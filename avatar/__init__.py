"""IsyMotron's avatar: a representation, never an authority.

Pure model only for AV1 (docs/AVATAR_ROADMAP.md): a bus that stamps channels
by source and renders a View. No I/O, no UI, no dependencies beyond the
stdlib.
"""

from avatar.model import AvatarBus, View
from avatar.protocol import ProtocolError, validate_event

__all__ = ["AvatarBus", "View", "ProtocolError", "validate_event"]
