"""Quine Gate state genealogy (milestone M5).

M4 gave a chain primitive (``state.sha = H(parent, transition)``). M5 turns it
into the thing the name promises: a machine that can answer *"what verifiable
state was I born from?"*

    GENESIS -> S0 --transition--> S1 --transition--> S2 -> ... -> HEAD

Each transition declares the operation, the input digests, the policy digest,
the artifact digest and the output digest. Because those live inside the hashed
``transition`` object, the state digest commits to all of them::

    state.sha = sha256(canonical({"parent": <parent sha>,
                                  "transition": {
                                      kind, label, operation,
                                      inputs, policy_digest,
                                      artifact_digest, output_digest, note}}))

The rule is enforced at *write* time, not only at verification: ``append``
refuses to build a state unless the caller names the current head as its
parent. A state with a wrong parent is not written at all -- "no state without
a verified parent".

This stays linear on purpose. A Merkle DAG is only worth it when branching is
real, and today it is not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .chain import CONFLICT, NOT_VERIFIABLE, PASS, REJECT, ChainVerification, make_state, verify_chain
from .canon import digest

TRANSITION_KINDS = frozenset({"genesis", "install", "configure", "execute"})


class GenealogyError(Exception):
    """A state could not be added; the genealogy is left unchanged."""


class ParentMismatch(GenealogyError):
    """The named parent is not the current head. The transition is halted."""


@dataclass(frozen=True)
class Transition:
    """What produced a state. Every digest here is sealed into the state."""

    kind: str
    label: str = ""
    operation: str = ""
    inputs: Sequence[str] = field(default_factory=tuple)
    policy_digest: str | None = None
    artifact_digest: str | None = None
    output_digest: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in TRANSITION_KINDS:
            raise GenealogyError(f"unknown transition kind {self.kind!r}")

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "operation": self.operation,
            "inputs": list(self.inputs),
            "policy_digest": self.policy_digest,
            "artifact_digest": self.artifact_digest,
            "output_digest": self.output_digest,
            "note": self.note,
        }

    @classmethod
    def genesis(cls, *, label: str = "S0", base_digest: str | None = None,
                note: str = "") -> "Transition":
        return cls(kind="genesis", label=label,
                   artifact_digest=base_digest, note=note)

    @classmethod
    def from_receipt(cls, receipt, *, label: str = "",
                     note: str = "") -> "Transition":
        """A transition that records a sealed execution receipt.

        `inputs` is the request intent, `artifact_digest` the capability that
        ran, `output_digest` the result. Everything the receipt claims is
        committed by the resulting state hash.
        """
        return cls(
            kind="execute",
            label=label,
            operation=receipt.capability,
            inputs=(receipt.request_digest,),
            policy_digest=receipt.policy_digest,
            artifact_digest=receipt.capability_digest,
            output_digest=receipt.result_digest,
            note=note or receipt.decision.decision.value,
        )


class Genealogy:
    """An append-only, linear, hash-chained ledger of states."""

    def __init__(self) -> None:
        self._states: list[dict] = []

    # -- read --------------------------------------------------------------
    @property
    def head(self) -> str | None:
        return self._states[-1]["sha"] if self._states else None

    @property
    def genesis(self) -> str | None:
        return self._states[0]["sha"] if self._states else None

    def __len__(self) -> int:
        return len(self._states)

    def states(self) -> list[dict]:
        return list(self._states)

    # -- write -------------------------------------------------------------
    def start(self, transition: Transition) -> dict:
        """Create the genesis state. Only valid once, on an empty genealogy."""
        if self._states:
            raise GenealogyError("genealogy already has a genesis")
        state = make_state(None, transition.to_dict())
        self._states.append(state)
        return state

    def append(self, parent_sha: str | None, transition: Transition) -> dict:
        """Append a state, but only from the current head.

        Naming anything else -- a stale state, a fork, or no parent at all --
        halts the transition and leaves the genealogy untouched.
        """
        if not self._states:
            raise GenealogyError("no genesis: call start() first")
        if parent_sha != self.head:
            raise ParentMismatch(
                f"parent {parent_sha!r} is not the current head {self.head!r}"
            )
        state = make_state(parent_sha, transition.to_dict())
        self._states.append(state)
        return state

    # -- load / serialise --------------------------------------------------
    @classmethod
    def from_states(cls, states: Sequence[Mapping[str, Any]]) -> "Genealogy":
        """Rehydrate a genealogy from stored states. Does not re-verify; call
        `verify_genealogy` for that."""
        ledger = cls()
        ledger._states = [dict(s) for s in states]
        return ledger

    def to_list(self) -> list[dict]:
        return list(self._states)


def verify_genealogy(states: Sequence[Mapping[str, Any]] | None, *,
                     anchored_genesis: str | None,
                     anchored_head: str | None) -> ChainVerification:
    """Verify a genealogy against externally anchored endpoints.

    Delegates to the M4 chain verifier: internal hash linkage, anchored
    genesis, anchored HEAD. Without both anchors the answer is
    ``NOT_VERIFIABLE``, never a fabricated PASS.
    """
    return verify_chain(states, anchored_genesis=anchored_genesis,
                        anchored_head=anchored_head)


def state_digest(parent_sha: str | None, transition: Transition) -> str:
    """The digest a state would have, without building it."""
    return digest({"parent": parent_sha, "transition": transition.to_dict()})
