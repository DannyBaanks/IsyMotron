"""The Malbolge learning pack. Imported only when asked for by name.

Nothing in IsyMotron core imports this package: the seam stays empty of
Malbolge semantics, and removing this directory leaves core behaviour intact
(that boundary is enforced by a gate test).
"""

from __future__ import annotations

from learning import Lesson, Verifier
from learning.packs.malbolge.lesson import LESSON
from learning.packs.malbolge.verifier import MalbolgeVerifier


def lesson() -> Lesson:
    return LESSON


def verifier() -> Verifier:
    return MalbolgeVerifier()


def advanced_lesson() -> Lesson:
    from learning.packs.malbolge.advanced import LESSON
    return LESSON


def advanced_verifier() -> Verifier:
    from learning.packs.malbolge.advanced import AdvancedMalbolgeVerifier
    return AdvancedMalbolgeVerifier()
