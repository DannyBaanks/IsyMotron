"""Process identity verification — the Volume Verifier pattern, applied to a
running process.

The shape is the same one that verifies a volume: normalized observations →
fingerprint (SHA-256 of the canonical form) → strength tier → verdict with
reason codes → a sealed store of known-good identities. The policy is the same
one too: evidence before narrative, no tier invented, read-only whenever
possible.

Measured scope (researcher experiment, 2026-09-22, Linux, same-uid attacker,
unprivileged observer):

What this DOES establish
  - instance identity: `pid` + `/proc/<pid>` inode + `starttime` separate two
    otherwise identical processes, and a reused pid is caught;
  - artifact drift: a binary deleted or replaced under a live process is
    caught (the path on disk and the running image diverge);
  - `execve`: `pid`+`starttime` survive an image replacement, and the artifact
    hash catches it.

What this does NOT establish
  - integrity of the running image: `exe_sha256` hashes the *file*, not the
    mapped memory — the two can differ;
  - benign behaviour: a malicious process has a perfectly verifiable identity;
  - independence from the kernel: `ps` and `/proc` are the same layer, so
    corroboration is single-layer. There is no STRONG tier and none is
    invented; an independent observer (hypervisor, TPM/measured boot) is a
    separate frontier, deliberately out of scope.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .canon import digest
from .seal import HMAC_SHA256, UNKEYED, resolve_key, seal_payload, verify_payload

# -- strengths (observation completeness, NOT a security level) --------------

WEAK = "WEAK"
STANDARD = "STANDARD"

# -- verdicts and reason codes (closed vocabulary; the else branch is not PASS)

PASS = "PASS"
DENY = "DENY"
ERROR = "ERROR"

UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
PROCESS_UNREADABLE = "PROCESS_UNREADABLE"
WEAK_OBSERVATIONS = "WEAK_OBSERVATIONS"
INSTANCE_MISMATCH = "INSTANCE_MISMATCH"
ARTIFACT_DELETED = "ARTIFACT_DELETED"
ARTIFACT_DRIFT = "ARTIFACT_DRIFT"
FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
BASELINE_UNSEALED = "BASELINE_UNSEALED"

#: Fields that carry *instance* identity. Ablating them makes two identical
#: commands collide (measured: scenario I2).
INSTANCE_FIELDS = ("pid", "proc_inode", "starttime")

STORE_CONTRACT = "isymotron-process-baseline/v1"


class ProcessError(Exception):
    """A process could not be observed or a baseline read."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def _unreadable(value: Any) -> bool:
    """Only a missing value or our explicit `<unreadable: ...>` marker counts.
    `pid` and `proc_inode` are ints, and an int is a perfectly good
    observation -- treating every non-string as unreadable made every process
    WEAK."""
    if value is None:
        return True
    return isinstance(value, str) and value.startswith("<")


@dataclass(frozen=True)
class ProcessIdentity:
    """What a process *is*, at the moment it was observed."""

    pid: int
    platform: str
    observations: Mapping[str, Any]
    fingerprint: str
    strength: str

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "platform": self.platform,
            "observations": dict(self.observations),
            "fingerprint": self.fingerprint,
            "strength": self.strength,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProcessIdentity":
        return cls(
            pid=int(data["pid"]),
            platform=str(data["platform"]),
            observations=dict(data["observations"]),
            fingerprint=str(data["fingerprint"]),
            strength=str(data["strength"]),
        )


@dataclass(frozen=True)
class Verdict:
    status: str
    reason: str | None
    detail: str
    strength: str

    def to_dict(self) -> dict:
        return {"status": self.status, "reason": self.reason,
                "detail": self.detail, "strength": self.strength}


# -- platform seam -----------------------------------------------------------

class ProcessSource(Protocol):
    platform: str

    def get_observations(self, pid: int) -> dict:  # pragma: no cover - protocol
        ...


class LinuxProcessSource:
    """Read-only observations from /proc. No root, no ptrace, no signals."""

    platform = "linux"

    def get_observations(self, pid: int) -> dict:
        base = f"/proc/{pid}"
        obs: dict[str, Any] = {"pid": pid}
        try:
            obs["proc_inode"] = os.stat(base).st_ino
        except OSError as exc:
            obs["proc_inode"] = f"<{exc.__class__.__name__}>"
        try:
            with open(f"{base}/stat", encoding="utf-8") as fh:
                stat = fh.read()
            # field 22 is starttime; `comm` may contain spaces/parens, so split
            # after the last ')'.
            fields = stat[stat.rfind(")") + 2:].split()
            obs["starttime"] = fields[19]
        except (OSError, IndexError) as exc:
            obs["starttime"] = f"<{exc.__class__.__name__}>"
        try:
            link = os.readlink(f"{base}/exe")
        except OSError as exc:
            link = f"<unreadable: {exc.__class__.__name__}>"
        obs["exe_link"] = link
        obs["exe_deleted"] = link.endswith(" (deleted)")
        try:
            # Reading through /proc keeps working after the file is unlinked,
            # which is what lets a *running* image be hashed after deletion.
            obs["exe_sha256"] = _sha256_file(f"{base}/exe")
        except OSError as exc:
            obs["exe_sha256"] = f"<unreadable: {exc.__class__.__name__}>"
        try:
            with open(f"{base}/status", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("Uid:"):
                        obs["uid"] = line.split()[1]
                        break
        except OSError as exc:
            obs["uid"] = f"<{exc.__class__.__name__}>"
        try:
            with open(f"{base}/cmdline", "rb") as fh:
                obs["cmdline"] = fh.read().decode("utf-8", "replace")
        except OSError as exc:
            obs["cmdline"] = f"<{exc.__class__.__name__}>"
        return obs


class UnsupportedProcessSource:
    """An explicit refusal, not a silent empty observation set."""

    platform = "unsupported"

    def get_observations(self, pid: int) -> dict:
        raise ProcessError(UNSUPPORTED_PLATFORM,
                           f"no process source for platform {sys.platform!r}")


def get_source() -> ProcessSource:
    return LinuxProcessSource() if sys.platform.startswith("linux") \
        else UnsupportedProcessSource()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def fingerprint(observations: Mapping[str, Any], *, instance: bool = True) -> str:
    """SHA-256 of the canonical observations. `instance=False` drops the
    instance fields on purpose — used to show what carries identity."""
    obs = dict(observations)
    if not instance:
        for key in INSTANCE_FIELDS:
            obs.pop(key, None)
    return digest(obs)


def strength_for(observations: Mapping[str, Any]) -> str:
    """STANDARD iff the instance fields are readable AND the executable
    artifact could be hashed; WEAK otherwise. Never STRONG."""
    if any(_unreadable(observations.get(k)) for k in INSTANCE_FIELDS):
        return WEAK
    if _unreadable(observations.get("exe_sha256")):
        return WEAK
    return STANDARD


def observe(pid: int, source: ProcessSource | None = None) -> ProcessIdentity:
    src = source or get_source()
    try:
        obs = src.get_observations(pid)
    except ProcessError:
        raise
    if _unreadable(obs.get("starttime")) and _unreadable(obs.get("proc_inode")):
        raise ProcessError(PROCESS_UNREADABLE, f"pid {pid} could not be observed")
    return ProcessIdentity(pid=pid, platform=src.platform, observations=obs,
                           fingerprint=fingerprint(obs), strength=strength_for(obs))


def verdict_for(baseline: ProcessIdentity, current: ProcessIdentity) -> Verdict:
    """Pure comparison. Fail-closed: an unreadable observation is ERROR, never
    PASS, and the order of checks is part of the contract."""
    b, c = baseline.observations, current.observations

    if any(_unreadable(c.get(k)) for k in INSTANCE_FIELDS):
        return Verdict(ERROR, WEAK_OBSERVATIONS,
                       "instance identity of the current process is unreadable", current.strength)

    if (b.get("pid") != c.get("pid") or b.get("starttime") != c.get("starttime")
            or b.get("proc_inode") != c.get("proc_inode")):
        return Verdict(DENY, INSTANCE_MISMATCH,
                       "pid was reused: this is not the observed instance", current.strength)

    if _unreadable(b.get("exe_sha256")):
        return Verdict(ERROR, WEAK_OBSERVATIONS,
                       "the baseline has no executable hash to compare", current.strength)
    if _unreadable(c.get("exe_sha256")):
        return Verdict(ERROR, WEAK_OBSERVATIONS,
                       "the executable of the current process is unreadable", current.strength)

    if c.get("exe_deleted") and not b.get("exe_deleted"):
        return Verdict(DENY, ARTIFACT_DELETED,
                       "the executable was unlinked under the live process", current.strength)
    if b.get("exe_sha256") != c.get("exe_sha256"):
        return Verdict(DENY, ARTIFACT_DRIFT,
                       "the executable image changed (execve or replacement)", current.strength)

    if current.fingerprint == baseline.fingerprint:
        return Verdict(PASS, None, "the process is the observed instance with the same artifact",
                       current.strength)
    return Verdict(DENY, FINGERPRINT_MISMATCH,
                   "instance and artifact match but another observation changed", current.strength)


def verify(pid: int, baseline: ProcessIdentity, *,
           source: ProcessSource | None = None) -> Verdict:
    try:
        current = observe(pid, source)
    except ProcessError as exc:
        return Verdict(ERROR, exc.reason, exc.detail, WEAK)
    return verdict_for(baseline, current)


# -- sealed store ------------------------------------------------------------

def save_baseline(path: str | Path, identity: ProcessIdentity,
                  key: str | None = None) -> None:
    """Atomic write (temp + rename) of a sealed baseline. The seal reuses the
    Quine Gate machinery; the key never lives in the store's directory."""
    payload = {"contract": STORE_CONTRACT, "identity": identity.to_dict()}
    skey = resolve_key(key)
    kind = HMAC_SHA256 if skey else UNKEYED
    document = dict(payload, seal_kind=kind,
                    seal=seal_payload(payload, kind=kind, key=key))
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(document, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, target)


def load_baseline(path: str | Path, key: str | None = None) -> ProcessIdentity:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProcessError(PROCESS_UNREADABLE, f"baseline unreadable: {exc}") from exc
    if data.get("contract") != STORE_CONTRACT:
        raise ProcessError(BASELINE_UNSEALED,
                           f"unknown store contract {data.get('contract')!r}")
    payload = {"contract": data["contract"], "identity": data["identity"]}
    if not verify_payload(payload, str(data.get("seal", "")),
                          kind=str(data.get("seal_kind", UNKEYED)), key=key):
        raise ProcessError(BASELINE_UNSEALED, "baseline seal does not verify")
    return ProcessIdentity.from_dict(data["identity"])
