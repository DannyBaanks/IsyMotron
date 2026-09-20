"""Doctor V0 gate: observed behaviour cannot silently exceed declarations."""

from isymotron.doctor import ActivityManifest, ObservedEffect, examine
from isymotron.verdicts import DoctorVerdict, Evidence


def test_declared_effects_get_scoped_pass_and_sealed_report():
    effect = ObservedEffect("filesystem.read", "activity://assets/input.txt")
    report = examine(
        ActivityManifest("lesson", "0.1", (effect.to_dict(),)), [effect]
    )
    assert report.verdict == DoctorVerdict.PASS_FOR_SCOPE
    assert report.evidence == Evidence.DEMONSTRATED
    assert report.undeclared_effects == ()
    assert report.verify()
    assert "SAFE" not in report.verdict.value


def test_undeclared_side_effect_blocks_promotion():
    declared = ObservedEffect("filesystem.read", "activity://assets/input.txt")
    escaped = ObservedEffect("filesystem.write", "hostfs://outside/result.txt", True)
    report = examine(ActivityManifest("lesson", "0.1", (declared.to_dict(),)), [declared, escaped])
    assert report.verdict == DoctorVerdict.DENY
    assert report.undeclared_effects == (escaped.to_dict(),)
    assert report.verify()


def test_no_observation_is_unknown_not_pass():
    report = examine(ActivityManifest("lesson", "0.1"), [])
    assert report.verdict == DoctorVerdict.UNKNOWN
    assert report.evidence == Evidence.UNKNOWN


def test_changed_artifact_denies_even_when_effects_match():
    artifact = {"entry": "main.py", "version": 1}
    manifest = ActivityManifest("lesson", "0.1", source_digest="sha256:old")
    report = examine(manifest, [], artifact=artifact)
    assert report.verdict == DoctorVerdict.DENY
    assert report.verify()
