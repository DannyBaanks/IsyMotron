"""Git registry gate: source is pinned, digested, then locally diagnosed."""

import json
import subprocess
import threading
from pathlib import Path

import pytest

from isymotron.doctor import DoctorVerdict
from isymotron.marketplace import GitActivityRegistry, manifest_digest, tree_digest
from isymotron.sandbox import PythonSandbox


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _activity_repo(tmp_path: Path, *, escaped: bool = False) -> tuple[Path, str]:
    repo = tmp_path / "activity-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "IsyMotron test")
    body = "from pathlib import Path\nPath('result.txt').write_text('ok')\n"
    if escaped:
        body = "from pathlib import Path\nPath('/outside-result.txt').write_text('no')\n"
    (repo / "main.py").write_text(body, encoding="utf-8")
    effects = [] if escaped else [{"kind": "filesystem.write", "target": "activity://result.txt", "mutation": True}]
    provisional = {"activity_id": "demo", "version": "0.1", "entrypoint": "main.py", "declared_effects": effects, "tree_digest": "", "manifest_digest": ""}
    (repo / "activity.json").write_text(json.dumps(provisional), encoding="utf-8")
    provisional["tree_digest"] = tree_digest(repo)
    provisional["manifest_digest"] = manifest_digest(type("Record", (), provisional)())
    (repo / "activity.json").write_text(json.dumps(provisional), encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "activity v0")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_install_pins_commit_verifies_tree_and_records_doctor(tmp_path):
    repo, commit = _activity_repo(tmp_path)
    installed = GitActivityRegistry().install(repo, commit, tmp_path / "installed")
    assert installed.commit == commit
    assert installed.record.activity_id == "demo"
    assert installed.report.verdict == DoctorVerdict.PASS_FOR_SCOPE
    assert (installed.path / "doctor-report.json").is_file()
    report = json.loads((installed.path / "doctor-report.json").read_text(encoding="utf-8"))
    assert report["git_commit"] == commit


def test_adversarial_activity_is_denied_locally(tmp_path):
    repo, commit = _activity_repo(tmp_path, escaped=True)
    installed = GitActivityRegistry().install(repo, commit, tmp_path / "installed")
    assert installed.report.verdict == DoctorVerdict.DENY
    assert installed.report.undeclared_effects


def test_changed_tree_is_rejected(tmp_path):
    repo, commit = _activity_repo(tmp_path)
    manifest = repo / "activity.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["tree_digest"] = "sha256:tampered"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    _git(repo, "add", "activity.json")
    _git(repo, "commit", "-qm", "tampered manifest")
    with pytest.raises(ValueError, match="tree digest mismatch"):
        GitActivityRegistry().install(repo, "HEAD", tmp_path / "installed")


def test_manifest_only_tampering_is_rejected(tmp_path):
    repo, _ = _activity_repo(tmp_path)
    manifest = repo / "activity.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["declared_effects"] = []
    manifest.write_text(json.dumps(data), encoding="utf-8")
    _git(repo, "add", "activity.json")
    _git(repo, "commit", "-qm", "tampered declarations")
    with pytest.raises(ValueError, match="manifest digest mismatch"):
        GitActivityRegistry().install(repo, "HEAD", tmp_path / "installed")


def test_concurrent_install_publishes_one_complete_snapshot(tmp_path):
    repo, commit = _activity_repo(tmp_path)
    barrier = threading.Barrier(2)

    class CoordinatedSandbox(PythonSandbox):
        def run(self, manifest, script):
            barrier.wait(timeout=10)
            return super().run(manifest, script)

    registry = GitActivityRegistry(CoordinatedSandbox())
    destination = tmp_path / "installed"
    results = []

    def install():
        try:
            results.append(("ok", registry.install(repo, commit, destination)))
        except Exception as exc:  # one winner, one deterministic loser
            results.append(("error", exc))

    workers = [threading.Thread(target=install) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=20)
    assert sorted(kind for kind, _ in results) == ["error", "ok"]
    assert (destination / "activity.json").is_file()
    assert (destination / "doctor-report.json").is_file()
    assert not list(destination.parent.glob(f".{destination.name}.staging-*"))


# -- fast path (claim G) -------------------------------------------------------

class CountingSandbox(PythonSandbox):
    def __init__(self):
        super().__init__()
        self.runs = 0

    def run(self, manifest, script):
        self.runs += 1
        return super().run(manifest, script)


def test_verified_activity_reuses_the_sealed_report_without_rerunning_the_sandbox(tmp_path):
    repo, commit = _activity_repo(tmp_path)
    sandbox = CountingSandbox()
    registry = GitActivityRegistry(sandbox, cache_path=tmp_path / "verify-cache.json")
    first = registry.install(repo, commit, tmp_path / "install-1")
    assert sandbox.runs == 1
    assert first.report.verify()

    second = registry.install(repo, commit, tmp_path / "install-2")
    assert sandbox.runs == 1, "fast path must not re-run the sandbox"
    assert second.report.payload() == first.report.payload()
    assert second.report.verify()
    replay = json.loads((second.path / "doctor-report.json").read_text(encoding="utf-8"))
    assert replay["verification"] == "reused"


def test_a_changed_activity_never_hits_the_fast_path(tmp_path):
    repo, commit = _activity_repo(tmp_path)
    sandbox = CountingSandbox()
    registry = GitActivityRegistry(sandbox, cache_path=tmp_path / "verify-cache.json")
    registry.install(repo, commit, tmp_path / "install-1")
    assert sandbox.runs == 1

    body = "from pathlib import Path\nPath('result.txt').write_text('v2')\n"
    (repo / "main.py").write_text(body, encoding="utf-8")
    manifest = repo / "activity.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["tree_digest"] = tree_digest(repo)
    data["manifest_digest"] = manifest_digest(type("Record", (), data)())
    manifest.write_text(json.dumps(data), encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "activity v2")

    third = registry.install(repo, "HEAD", tmp_path / "install-3")
    assert sandbox.runs == 2, "changed bits must be re-verified, not replayed"
    assert third.report.verify()


def test_a_tampered_cache_reverts_to_full_verification(tmp_path):
    repo, commit = _activity_repo(tmp_path)
    sandbox = CountingSandbox()
    cache = tmp_path / "verify-cache.json"
    registry = GitActivityRegistry(sandbox, cache_path=cache)
    registry.install(repo, commit, tmp_path / "install-1")

    data = json.loads(cache.read_text(encoding="utf-8"))
    entry = next(iter(data["entries"].values()))
    entry["report"]["activity_version"] = "9.9"  # valid shape, broken seal
    cache.write_text(json.dumps(data), encoding="utf-8")

    registry.install(repo, commit, tmp_path / "install-2")
    assert sandbox.runs == 2, "a forged cache entry must fail its seal and re-run"
    replay = json.loads((tmp_path / "install-2" / "doctor-report.json").read_text(encoding="utf-8"))
    assert replay["verification"] == "sandbox"


def test_adversarial_activities_are_never_cached(tmp_path):
    repo, commit = _activity_repo(tmp_path, escaped=True)
    sandbox = CountingSandbox()
    registry = GitActivityRegistry(sandbox, cache_path=tmp_path / "verify-cache.json")
    registry.install(repo, commit, tmp_path / "install-1")
    registry.install(repo, commit, tmp_path / "install-2")
    assert sandbox.runs == 2, "a DENY is re-proven every time, never replayed"
