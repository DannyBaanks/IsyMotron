"""Process identity verifier — the measured scenarios as a regression gate.

Cross-platform half (runs on Windows CI too): `verdict_for` is pure, the
unsupported platform refuses explicitly, and the sealed store round-trips.
Linux half (skipped elsewhere, like test_linux_power.py): the scenarios the
researcher measured on 2026-09-22 — stability, instance identity, field
ablation, artifact drift, execve, observer limits, CLI exit codes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from isymotron.process import (
    ARTIFACT_DELETED,
    ARTIFACT_DRIFT,
    BASELINE_UNSEALED,
    DENY,
    ERROR,
    FINGERPRINT_MISMATCH,
    INSTANCE_MISMATCH,
    PASS,
    STANDARD,
    UNSUPPORTED_PLATFORM,
    WEAK,
    WEAK_OBSERVATIONS,
    LinuxProcessSource,
    ProcessError,
    ProcessIdentity,
    UnsupportedProcessSource,
    fingerprint,
    get_source,
    load_baseline,
    observe,
    save_baseline,
    strength_for,
    verdict_for,
    verify,
)

REPO = Path(__file__).resolve().parent.parent
LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"),
                           reason="process source is Linux-only for now")


def _identity(*, pid=100, starttime="500", inode=42, exe="sha256:" + "a" * 64,
              deleted=False, cmdline="sleep 5", uid="1000") -> ProcessIdentity:
    obs = {
        "pid": pid, "proc_inode": inode, "starttime": starttime,
        "exe_sha256": exe, "exe_deleted": deleted, "exe_link": "/bin/sleep",
        "cmdline": cmdline, "uid": uid,
    }
    return ProcessIdentity(pid=pid, platform="linux", observations=obs,
                           fingerprint=fingerprint(obs), strength=strength_for(obs))


# -- verdict logic (pure; runs everywhere) ----------------------------------

def test_identical_identity_passes():
    v = verdict_for(_identity(), _identity())
    assert v.status == PASS and v.reason is None and v.strength == STANDARD


def test_reused_pid_is_instance_mismatch():
    """Same pid, different starttime/inode == a different process instance."""
    v = verdict_for(_identity(), _identity(starttime="999", inode=77))
    assert v.status == DENY and v.reason == INSTANCE_MISMATCH


def test_changed_image_is_artifact_drift():
    """execve: instance survives, the image does not."""
    v = verdict_for(_identity(), _identity(exe="sha256:" + "b" * 64))
    assert v.status == DENY and v.reason == ARTIFACT_DRIFT


def test_deleted_binary_is_artifact_deleted():
    v = verdict_for(_identity(), _identity(deleted=True))
    assert v.status == DENY and v.reason == ARTIFACT_DELETED


def test_unreadable_current_artifact_is_error_not_pass():
    v = verdict_for(_identity(), _identity(exe="<unreadable: PermissionError>"))
    assert v.status == ERROR and v.reason == WEAK_OBSERVATIONS


def test_unreadable_baseline_artifact_is_error_not_pass():
    v = verdict_for(_identity(exe="<unreadable: FileNotFoundError>"), _identity())
    assert v.status == ERROR and v.reason == WEAK_OBSERVATIONS


def test_other_observation_change_is_fingerprint_mismatch():
    v = verdict_for(_identity(), _identity(cmdline="sleep 6"))
    assert v.status == DENY and v.reason == FINGERPRINT_MISMATCH


def test_weak_strength_when_artifact_unreadable():
    assert strength_for({"pid": 1, "proc_inode": 2, "starttime": "3",
                         "exe_sha256": "<unreadable: PermissionError>"}) == WEAK


def test_unsupported_source_refuses_explicitly():
    with pytest.raises(ProcessError) as excinfo:
        UnsupportedProcessSource().get_observations(1)
    assert excinfo.value.reason == UNSUPPORTED_PLATFORM


def test_supported_platform_selection():
    source = get_source()
    if sys.platform.startswith("linux"):
        assert isinstance(source, LinuxProcessSource)
        assert source.platform == "linux"
    else:
        assert isinstance(source, UnsupportedProcessSource)


# -- sealed store (runs everywhere) -----------------------------------------

def test_store_roundtrips_and_detects_tampering(tmp_path):
    path = tmp_path / "proc.baseline.json"
    save_baseline(path, _identity())
    loaded = load_baseline(path)
    assert loaded.fingerprint == _identity().fingerprint

    data = json.loads(path.read_text(encoding="utf-8"))
    data["identity"]["observations"]["cmdline"] = "evil --payload"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProcessError) as excinfo:
        load_baseline(path)
    assert excinfo.value.reason == BASELINE_UNSEALED


def test_store_is_atomic_and_has_no_key_next_to_it(tmp_path):
    path = tmp_path / "proc.baseline.json"
    save_baseline(path, _identity(), key="secret-key")
    assert not (tmp_path / "proc.baseline.json.tmp").exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["seal_kind"] == "hmac-sha256"
    assert "secret-key" not in path.read_text(encoding="utf-8")


# -- measured scenarios against real processes (Linux only) -----------------

def _spawn(argv):
    return subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def _observe_quietly(pid):
    """observe() or None if the process is already gone."""
    try:
        return observe(pid)
    except ProcessError:
        return None


def _wait_until(fn, timeout=10.0, interval=0.05):
    """Poll instead of trusting a fixed sleep: these tests run alongside ~380
    others and a fixed sleep flaked under that load."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = fn()
        if got is not None:
            return got
        time.sleep(interval)
    return None


def _cleanup(*procs):
    for proc in procs:
        try:
            proc.kill()
        except Exception:
            pass


@LINUX
def test_scenario_C_stability_within_one_instance():
    proc = _spawn(["sleep", "20"])
    time.sleep(0.10)
    try:
        first = observe(proc.pid)
        second = observe(proc.pid)
        assert first.fingerprint == second.fingerprint
        assert verify(proc.pid, first).status == PASS
    finally:
        _cleanup(proc)


@LINUX
def test_scenario_I1_I2_instance_identity_and_field_ablation():
    a = _spawn(["sleep", "20"])
    b = _spawn(["sleep", "20"])
    time.sleep(0.10)
    try:
        ia, ib = observe(a.pid), observe(b.pid)
        assert ia.fingerprint != ib.fingerprint, "two instances must not collide"
        assert fingerprint(ia.observations, instance=False) == \
            fingerprint(ib.observations, instance=False), \
            "without the instance fields they must collide: that is what carries identity"
    finally:
        _cleanup(a, b)


@LINUX
def test_scenario_D_binary_deleted_under_a_live_process(tmp_path):
    fake = tmp_path / "victim.bin"
    fake.write_bytes(Path("/bin/sleep").read_bytes())
    fake.chmod(0o755)
    proc = _spawn([str(fake), "20"])
    time.sleep(0.10)
    try:
        baseline = observe(proc.pid)
        fake.unlink()
        time.sleep(0.05)
        current = observe(proc.pid)
        assert current.observations["exe_deleted"] is True
        verdict = verdict_for(baseline, current)
        assert verdict.status == DENY and verdict.reason == ARTIFACT_DELETED

        # a different file now owns the path: disk != running image
        replacement = tmp_path / "replacement.bin"
        replacement.write_bytes(b"# not the running image\n")
        os.replace(replacement, fake)
        from isymotron.process import _sha256_file
        assert _sha256_file(str(fake)) != current.observations["exe_sha256"]
    finally:
        _cleanup(proc)


@LINUX
def test_scenario_X_execve_keeps_instance_and_changes_artifact():
    # `exec` into a LONG-LIVED image: `/bin/true` exits at once, which leaves a
    # zombie whose /proc/<pid>/exe is unreadable. The original researcher run
    # compared against that unreadable marker, not against a live new image;
    # this is the corrected measurement.
    #
    # Timing is polled, never slept on: the fixed-sleep version flaked when the
    # whole suite ran on a loaded machine.
    proc = _spawn(["bash", "-c", "sleep 1.5; exec sleep 30"])
    try:
        baseline = _wait_until(lambda: _observe_quietly(proc.pid))
        assert baseline is not None, "the shell never became observable"
        assert not str(baseline.observations["exe_sha256"]).startswith("<"), \
            "the baseline image must be readable"

        current = _wait_until(lambda: (lambda c: c if (
            c is not None
            and c.observations["exe_sha256"] != baseline.observations["exe_sha256"]
        ) else None)(_observe_quietly(proc.pid)))
        assert current is not None, "execve never happened within the timeout"

        assert current.observations["starttime"] == baseline.observations["starttime"], \
            "instance identity survives execve"
        assert not str(current.observations["exe_sha256"]).startswith("<"), \
            "the new image must be readable, or the test proves nothing"
        verdict = verdict_for(baseline, current)
        assert verdict.status == DENY and verdict.reason == ARTIFACT_DRIFT
    finally:
        _cleanup(proc)


@LINUX
def test_scenario_P_observer_limit_degrades_strength():
    identity = observe(1)  # init: not ours
    if str(identity.observations["exe_sha256"]).startswith("<"):
        assert identity.strength == WEAK
    else:  # running as root or a permissive host
        assert identity.strength in (WEAK, STANDARD)


@LINUX
def test_cli_observe_store_verify_exit_codes(tmp_path):
    proc = _spawn(["sleep", "20"])
    time.sleep(0.10)
    baseline = tmp_path / "proc.baseline.json"
    script = str(REPO / "tools" / "process_verify.py")
    try:
        store = subprocess.run([sys.executable, script, "store", str(proc.pid),
                                "--baseline", str(baseline)],
                               capture_output=True, text=True)
        assert store.returncode == 0, store.stderr

        ok = subprocess.run([sys.executable, script, "verify", str(proc.pid),
                             "--baseline", str(baseline)],
                            capture_output=True, text=True)
        assert ok.returncode == 0, ok.stdout
        assert json.loads(ok.stdout)["status"] == PASS

        proc.kill()
        proc.wait()
        dead = subprocess.run([sys.executable, script, "verify", str(proc.pid),
                               "--baseline", str(baseline)],
                              capture_output=True, text=True)
        assert dead.returncode == 2, dead.stdout
    finally:
        _cleanup(proc)


@LINUX
def test_cli_missing_baseline_is_error(tmp_path):
    script = str(REPO / "tools" / "process_verify.py")
    result = subprocess.run([sys.executable, script, "verify", "1",
                             "--baseline", str(tmp_path / "nope.json")],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "NO_BASELINE"
