"""Local grant file. This file IS the local authority (invariant 2.7).

No cloud record, marketplace badge or model can widen what is written here.
The only way to grant a capability on this machine is for a human to sit at it
and edit this file, or use `tools/host_cli.py grant`.

Deny-by-default is literal: a missing or unreadable grant file yields a host
with zero granted capabilities. It boots inert rather than boots open.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

def _default_path() -> str:
    """Where the grant file lives. The file FORMAT is one contract for every
    host; only its location follows the OS convention."""
    import sys
    if sys.platform.startswith("linux"):
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config")
        return os.path.join(base, "isymotron", "grants.json")
    return os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "IsyMotron", "grants.json",
    )


DEFAULT_PATH = _default_path()


@dataclass
class Grants:
    host_id: str
    display_name: str
    granted: list[str]
    scopes: dict[str, dict[str, Any]]
    admin_granted: bool = False
    max_lease_ttl_s: float = 900.0
    source: str = "<none>"

    @staticmethod
    def inert(reason: str) -> "Grants":
        """A host with no authority at all. Still a valid, describable host."""
        return Grants(
            host_id=_default_host_id(), display_name=_default_display_name(),
            granted=[], scopes={}, source=f"<inert: {reason}>",
        )

    @staticmethod
    def load(path: str | None = None) -> "Grants":
        path = path or DEFAULT_PATH
        if not os.path.isfile(path):
            return Grants.inert(f"no grant file at {path}")
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as exc:
            # A grant file we cannot parse is not "no restrictions". It is no
            # authority. Failing open here would undo the whole product.
            return Grants.inert(f"unreadable grant file: {type(exc).__name__}")

        granted = [str(c) for c in raw.get("granted", [])]
        scopes = {str(k): dict(v) for k, v in (raw.get("scopes") or {}).items()}
        # A capability granted with no scope entry gets an empty scope, which
        # every scope checker treats as a refusal.
        for cap in granted:
            scopes.setdefault(cap, {})
        return Grants(
            host_id=str(raw.get("host_id") or _default_host_id()),
            display_name=str(raw.get("display_name") or _default_display_name()),
            granted=granted,
            scopes=scopes,
            admin_granted=bool(raw.get("admin_granted", False)),
            max_lease_ttl_s=float(raw.get("max_lease_ttl_s", 900.0)),
            source=path,
        )

    def save(self, path: str | None = None) -> str:
        path = path or DEFAULT_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "host_id": self.host_id,
            "display_name": self.display_name,
            "granted": self.granted,
            "scopes": self.scopes,
            "admin_granted": self.admin_granted,
            "max_lease_ttl_s": self.max_lease_ttl_s,
        }
        # utf-8, never utf-8-sig: a BOM here would make the file unparseable
        # and silently demote the host to inert.
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        self.source = path
        return path


def _default_host_id() -> str:
    import platform
    import sys
    node = platform.node().lower().replace(" ", "-") or "unknown"
    if sys.platform.startswith("linux"):
        return f"linux-{node}"
    rel = platform.win32_ver()[1].split(".")
    tag = "win11" if len(rel) > 2 and int(rel[2]) >= 22000 else "win"
    return f"{tag}-{node}"


def _default_display_name() -> str:
    """What a person calls this machine, not what the registry calls it."""
    import platform
    import sys
    if sys.platform.startswith("linux"):
        return f"{platform.node()} — Linux"
    parts = platform.win32_ver()[1].split(".")
    build = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    release = "11" if build >= 22000 else "10"
    return f"{platform.node()} — Windows {release}"
