"""The Doctor's deterministic verification plane.

The Doctor does not execute activities.  A sandbox/provider supplies an
observation trace; this module compares that trace with the activity's
declared effects and produces a scoped verdict.  Keeping this boundary pure is
intentional: the next milestone can add a sandbox without changing the
authority or verdict contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from .canon import digest
from .verdicts import DoctorVerdict, Evidence


@dataclass(frozen=True)
class ActivityManifest:
    """The source-level claims an activity makes about its effects."""

    activity_id: str
    version: str
    declared_effects: tuple[Mapping[str, Any], ...] = ()
    source_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "version": self.version,
            "declared_effects": [dict(effect) for effect in self.declared_effects],
            "source_digest": self.source_digest,
        }


@dataclass(frozen=True)
class ObservedEffect:
    """One effect reported by a trusted observation provider."""

    kind: str
    target: str
    mutation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DoctorReport:
    """A scoped machine report; deliberately never says ``SAFE``."""

    activity_id: str
    activity_version: str
    activity_digest: str
    verdict: DoctorVerdict
    evidence: Evidence
    declared_effects: tuple[Mapping[str, Any], ...]
    observed_effects: tuple[Mapping[str, Any], ...]
    undeclared_effects: tuple[Mapping[str, Any], ...]
    seal: str

    def payload(self) -> dict[str, Any]:
        return {
            "contract": "Doctor/v0",
            "activity_id": self.activity_id,
            "activity_version": self.activity_version,
            "activity_digest": self.activity_digest,
            "verdict": self.verdict.value,
            "evidence": self.evidence.value,
            "declared_effects": [dict(x) for x in self.declared_effects],
            "observed_effects": [dict(x) for x in self.observed_effects],
            "undeclared_effects": [dict(x) for x in self.undeclared_effects],
        }

    def verify(self) -> bool:
        return self.seal == digest(self.payload())


def _effect_key(effect: Mapping[str, Any]) -> str:
    return digest(dict(effect))


def examine(
    manifest: ActivityManifest,
    observed: Iterable[ObservedEffect | Mapping[str, Any]],
    *,
    artifact: Any = None,
) -> DoctorReport:
    """Compare observed effects with declarations and seal the result.

    ``artifact`` is optional in V0.  When supplied, its canonical digest must
    match ``manifest.source_digest``; a mismatch is a hard ``DENY``.  This is
    the changed-artifact rule without pretending that a provider exists yet.
    """
    declared = tuple(dict(effect) for effect in manifest.declared_effects)
    observed_dicts = tuple(
        item.to_dict() if isinstance(item, ObservedEffect) else dict(item)
        for item in observed
    )
    declared_keys = {_effect_key(effect) for effect in declared}
    undeclared = tuple(
        effect for effect in observed_dicts if _effect_key(effect) not in declared_keys
    )
    digest_mismatch = (
        artifact is not None
        and manifest.source_digest is not None
        and digest(artifact) != manifest.source_digest
    )
    verdict = (
        DoctorVerdict.DENY
        if undeclared or digest_mismatch
        else DoctorVerdict.PASS_FOR_SCOPE if observed_dicts else DoctorVerdict.UNKNOWN
    )
    report = DoctorReport(
        activity_id=manifest.activity_id,
        activity_version=manifest.version,
        activity_digest=manifest.source_digest or digest(manifest.to_dict()),
        verdict=verdict,
        evidence=Evidence.DEMONSTRATED if observed_dicts else Evidence.UNKNOWN,
        declared_effects=declared,
        observed_effects=observed_dicts,
        undeclared_effects=undeclared,
        seal="",
    )
    return DoctorReport(**{**asdict(report), "verdict": verdict,
                           "evidence": report.evidence,
                           "seal": digest(report.payload())})
