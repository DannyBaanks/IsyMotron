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

import ctypes
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


class WindowsProcessSource:
    """Read-only observations from Win32 handles (ctypes only, no third party).

    Instance identity is ``pid`` + ``CreationTime`` from ``GetProcessTimes``
    (measured step 1, E2: PID reuse always shows a new CreationTime).
    Windows has no ``/proc/<pid>`` inode, so ``proc_inode`` is *defined*
    equal to ``starttime``: a CreationTime-derived identity, not an
    independent handle.

    ``exe_deleted`` is always ``False``: the loader holds the running image
    with an exclusive share lock, so deleting or replacing the file under a
    live process is refused (measured step 1, E3: ``WinError 5`` /
    ``Errno 13``) instead of being observable. There is nothing to detect,
    so no reason code is invented for it.

    ``cmdline`` is a best-effort raw read of ``CommandLine`` from the
    target's PEB (same-bitness only); COM/WMI is deliberately not used.
    Every failure path yields an explicit ``<unreadable: ...>`` marker,
    never a silent empty value.
    """

    platform = "windows"

    def get_observations(self, pid: int) -> dict:
        if sys.platform != "win32":
            raise ProcessError(UNSUPPORTED_PLATFORM,
                               "WindowsProcessSource needs sys.platform == 'win32'")
        import ctypes
        from ctypes import wintypes

        k = ctypes.windll.kernel32
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = (wintypes.HANDLE,)
        k.CloseHandle.restype = wintypes.BOOL
        k.GetLastError.restype = wintypes.DWORD

        obs: dict[str, Any] = {"pid": pid}
        # PROCESS_QUERY_LIMITED_INFORMATION: enough for times + image path.
        handle, err = _win_open(k, pid, 0x1000)
        if handle is None:
            marker = f"<unreadable: OpenProcess error {err}>"
            obs.update({
                "proc_inode": marker, "starttime": marker,
                "exe_link": marker, "exe_deleted": False,
                "exe_sha256": marker, "uid": marker, "cmdline": marker,
            })
            return obs
        try:
            creation = _win_creation(k, handle)
            if creation is None:
                marker = "<unreadable: GetProcessTimes>"
                obs["starttime"] = marker
                obs["proc_inode"] = marker
            else:
                # No inode analog on Windows: identity IS the CreationTime.
                obs["starttime"] = str(creation)
                obs["proc_inode"] = str(creation)
            # Loader lock (step-1 E3): unlink/replace is refused, not observable.
            obs["exe_deleted"] = False
            image = _win_image(k, handle)
            if image is None:
                obs["exe_link"] = "<unreadable: QueryFullProcessImageNameW>"
                obs["exe_sha256"] = "<unreadable: no image path>"
            else:
                obs["exe_link"] = image
                try:
                    obs["exe_sha256"] = _sha256_file(image)
                except OSError as exc:
                    obs["exe_sha256"] = f"<unreadable: {exc.__class__.__name__}>"
            obs["uid"] = _win_owner_sid(k, handle)
            obs["cmdline"] = _win_cmdline(k, handle, pid)
        finally:
            k.CloseHandle(handle)
        return obs


class _WinFileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]


def _win_open(k, pid: int, access: int):
    """OpenProcess wrapper: (handle, None) or (None, GetLastError)."""
    handle = k.OpenProcess(access, False, pid)
    if not handle:
        return None, k.GetLastError()
    return handle, None


def _win_creation(k, handle):
    """Combined CreationTime FILETIME, or None."""
    import ctypes
    from ctypes import wintypes
    k.GetProcessTimes.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(_WinFileTime), ctypes.POINTER(_WinFileTime),
        ctypes.POINTER(_WinFileTime), ctypes.POINTER(_WinFileTime))
    k.GetProcessTimes.restype = wintypes.BOOL
    ct, et, kt, ut = _WinFileTime(), _WinFileTime(), _WinFileTime(), _WinFileTime()
    if not k.GetProcessTimes(handle, ctypes.byref(ct), ctypes.byref(et),
                             ctypes.byref(kt), ctypes.byref(ut)):
        return None
    return (ct.high << 32) | ct.low


def _win_image(k, handle) -> str | None:
    """Full image path via QueryFullProcessImageNameW, or None."""
    import ctypes
    from ctypes import wintypes
    k.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD))
    k.QueryFullProcessImageNameW.restype = wintypes.BOOL
    buf = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buf))
    if not k.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
        return None
    return buf.value


def _win_owner_sid(k, handle) -> str:
    """Owner SID string via OpenProcessToken + GetTokenInformation."""
    import ctypes
    from ctypes import wintypes
    k.OpenProcessToken.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    k.OpenProcessToken.restype = wintypes.BOOL
    tok = wintypes.HANDLE()
    if not k.OpenProcessToken(handle, 0x0008, ctypes.byref(tok)):  # TOKEN_QUERY
        return f"<unreadable: OpenProcessToken error {k.GetLastError()}>"
    try:
        adv = ctypes.windll.advapi32
        adv.GetTokenInformation.argtypes = (
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
        adv.GetTokenInformation.restype = wintypes.BOOL
        need = wintypes.DWORD(0)
        adv.GetTokenInformation(tok, 1, None, 0, ctypes.byref(need))  # TokenUser; size probe
        if not need.value:
            return f"<unreadable: GetTokenInformation error {k.GetLastError()}>"
        raw = ctypes.create_string_buffer(need.value)
        if not adv.GetTokenInformation(tok, 1, raw, need, ctypes.byref(need)):
            return f"<unreadable: GetTokenInformation error {k.GetLastError()}>"
        ptr_size = ctypes.sizeof(ctypes.c_void_p)
        sid_addr = int.from_bytes(raw.raw[:ptr_size], "little")
        if not sid_addr:
            return "<unreadable: null SID>"
        adv.ConvertSidToStringSidW.argtypes = (wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR))
        adv.ConvertSidToStringSidW.restype = wintypes.BOOL
        out = wintypes.LPWSTR()
        if not adv.ConvertSidToStringSidW(sid_addr, ctypes.byref(out)):
            return f"<unreadable: ConvertSidToStringSid error {k.GetLastError()}>"
        try:
            return out.value
        finally:
            k.LocalFree.argtypes = (wintypes.HANDLE,)
            k.LocalFree.restype = wintypes.HANDLE
            k.LocalFree(out)
    finally:
        k.CloseHandle(tok)


def _win_is_wow64(k, handle) -> bool:
    """True if the target is a 32-bit process under 64-bit Windows."""
    import ctypes
    from ctypes import wintypes
    k.IsWow64Process.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
    k.IsWow64Process.restype = wintypes.BOOL
    flag = wintypes.BOOL(False)
    if not k.IsWow64Process(handle, ctypes.byref(flag)):
        return False
    return bool(flag.value)


def _win_read(k, handle, address: int, size: int):
    """ReadProcessMemory wrapper: bytes or None."""
    import ctypes
    from ctypes import wintypes
    k.ReadProcessMemory.argtypes = (
        wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID,
        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
    k.ReadProcessMemory.restype = wintypes.BOOL
    buf = ctypes.create_string_buffer(size)
    done = ctypes.c_size_t(0)
    if not k.ReadProcessMemory(handle, address, buf, size, ctypes.byref(done)):
        return None
    return buf.raw[:done.value]


def _win_peb(k, handle):
    """PEB base address via NtQueryInformationProcess, or None."""
    import ctypes
    ntdll = ctypes.windll.ntdll
    ntdll.NtQueryInformationProcess.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
        ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong))
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    ptr = ctypes.sizeof(ctypes.c_void_p)
    buf = ctypes.create_string_buffer(ptr * 6)
    retlen = ctypes.c_ulong(0)
    if ntdll.NtQueryInformationProcess(handle, 0, buf, len(buf),
                                       ctypes.byref(retlen)) != 0:
        return None
    return int.from_bytes(buf.raw[ptr:2 * ptr], "little")


def _win_cmdline(k, handle, pid: int) -> str:
    """Raw CommandLine from the target's PEB; unreadable marker on failure.

    PEB offsets used (stable across Windows 10/11):
    64-bit PEB.ProcessParameters at +0x20, CommandLine at params +0x70;
    32-bit PEB.ProcessParameters at +0x10, CommandLine at params +0x40.
    Cross-bitness reads are refused explicitly instead of guessing.
    """
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    probe, err = _win_open(k, pid, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ)
    if probe is None:
        return f"<unreadable: OpenProcess error {err}>"
    try:
        import ctypes
        ptr = ctypes.sizeof(ctypes.c_void_p)
        if ptr == 8:
            if _win_is_wow64(k, probe):
                return "<unreadable: cross-bitness PEB read not implemented>"
            peb_off, cmd_off, addr_off = 0x20, 0x70, 8
        elif ptr == 4:
            if not _win_is_wow64(k, probe):
                return "<unreadable: cross-bitness PEB read not implemented>"
            peb_off, cmd_off, addr_off = 0x10, 0x40, 4
        else:
            return "<unreadable: unknown pointer size>"
        peb = _win_peb(k, probe)
        if peb is None:
            return "<unreadable: NtQueryInformationProcess>"
        params_raw = _win_read(k, probe, peb + peb_off, ptr)
        if params_raw is None:
            return "<unreadable: PEB.ProcessParameters>"
        params = int.from_bytes(params_raw, "little")
        if not params:
            return "<unreadable: null ProcessParameters>"
        # UNICODE_STRING: Length@0 (u16), Buffer@(8|4).
        cmd_raw = _win_read(k, probe, params + cmd_off, 16 if ptr == 8 else 8)
        if cmd_raw is None:
            return "<unreadable: RTL_USER_PROCESS_PARAMETERS.CommandLine>"
        length = int.from_bytes(cmd_raw[:2], "little")
        buf_addr = int.from_bytes(cmd_raw[addr_off:addr_off + ptr], "little")
        if not buf_addr or not length or length > 32768:
            return "<unreadable: empty CommandLine>"
        text_raw = _win_read(k, probe, buf_addr, length)
        if text_raw is None:
            return "<unreadable: CommandLine buffer>"
        return text_raw.decode("utf-16-le", "replace").rstrip("\x00")
    finally:
        k.CloseHandle(probe)


class UnsupportedProcessSource:
    """An explicit refusal, not a silent empty observation set."""

    platform = "unsupported"

    def get_observations(self, pid: int) -> dict:
        raise ProcessError(UNSUPPORTED_PLATFORM,
                           f"no process source for platform {sys.platform!r}")


def get_source() -> ProcessSource:
    if sys.platform.startswith("linux"):
        return LinuxProcessSource()
    if sys.platform == "win32":
        return WindowsProcessSource()
    return UnsupportedProcessSource()


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
