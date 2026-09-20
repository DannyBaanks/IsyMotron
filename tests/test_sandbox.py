"""Sandbox V0: real activity traces feed the Doctor."""

from pathlib import Path

from isymotron.doctor import ActivityManifest, DoctorVerdict
from isymotron.sandbox import PythonSandbox


def _activity(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "activity.py"
    script.write_text(body, encoding="utf-8")
    return script


def test_declared_write_passes_with_real_trace(tmp_path):
    script = _activity(tmp_path, "from pathlib import Path\nPath('result.txt').write_text('ok')\n")
    manifest = ActivityManifest(
        "writer", "0.1",
        ({"kind": "filesystem.write", "target": "activity://result.txt", "mutation": True},),
    )
    result = PythonSandbox().run(manifest, script)
    assert result.exit_code == 0
    assert result.report.verdict == DoctorVerdict.PASS_FOR_SCOPE
    assert result.report.verify()


def test_outside_write_is_blocked_and_denied(tmp_path):
    outside = tmp_path / "outside.txt"
    script = _activity(
        tmp_path,
        f"from pathlib import Path\ntry:\n Path(r'{outside}').write_text('nope')\nexcept PermissionError:\n pass\n",
    )
    result = PythonSandbox().run(ActivityManifest("escape", "0.1"), script)
    assert result.exit_code == 0
    assert result.report.verdict == DoctorVerdict.DENY
    assert any(effect.target.startswith("hostfs://") for effect in result.effects)
    assert not outside.exists()


def test_process_creation_is_blocked_and_denied(tmp_path):
    script = _activity(tmp_path, "import subprocess\nsubprocess.run(['whoami'])\n")
    result = PythonSandbox().run(ActivityManifest("spawner", "0.1"), script)
    assert result.report.verdict == DoctorVerdict.DENY
    assert any(effect.kind == "process.spawn" for effect in result.effects)
