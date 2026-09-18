"""Logical resources: the model names a resource, the host knows where it is.

A grant is physical (`C:/Users/me/Pictures/Demo`, `C:/Games/DOOM.EXE`). What a
planner sees is logical (`hostfs://demo`, `doom`). The two halves never meet
outside the host:

- `logical_bounds()` is the only view that leaves the machine. It carries ids,
  URIs and labels, never a physical path. A model provider never learns the
  user's name or folder layout.
- `resolve_path()` / `resolve_app()` translate back, on the host, against the
  lease's scope. A name that is not granted resolves to nothing, and nothing
  is a DENY -- the model cannot name its way out of a root.

Before this, the catalogue said "inside the granted roots" without saying
which, so a plan could only succeed by guessing a path. A refusal caused by
hiding what the model needed proves nothing about authority. See
docs/FINDINGS.md #9.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Any, Mapping

SCHEME = "hostfs://"


def normalize_path(p: str) -> str:
    """One path grammar for every host generation.

    Win98 and Win11 disagree about separators and case; the contract does not.
    Backslashes fold to '/', drive letters uppercase, case-insensitive compare
    is done by the caller on the normalized form.
    """
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].upper() + p[1:]
    p = posixpath.normpath(p)
    return p


def under(root: str, path: str) -> bool:
    """True iff `path` is `root` or lives beneath it. Rejects '..' escapes,
    and rejects sibling prefixes ('/Photos2' is not under '/Photos')."""
    r = normalize_path(root).rstrip("/").lower()
    q = normalize_path(path).rstrip("/").lower()
    return q == r or q.startswith(r + "/")


def _slug(name: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or fallback


def _unique(ids: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i in ids:
        seen[i] = seen.get(i, 0) + 1
        out.append(i if seen[i] == 1 else f"{i}-{seen[i]}")
    return out


# --------------------------------------------------------------------------
# Filesystem roots
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FsRoot:
    id: str
    label: str
    path: str          # physical; never leaves the host

    @property
    def uri(self) -> str:
        return SCHEME + self.id


def fs_roots(scope: Mapping[str, Any]) -> list[FsRoot]:
    """A grant's roots, named. A plain string is named after its folder;
    `{"id", "label", "path"}` keeps the names the human chose."""
    raw = []
    for entry in scope.get("roots") or []:
        if isinstance(entry, str):
            label = posixpath.basename(normalize_path(entry).rstrip("/")) or entry
            raw.append((_slug(label, "root"), label, entry))
        elif isinstance(entry, Mapping) and isinstance(entry.get("path"), str):
            path = entry["path"]
            label = str(entry.get("label")
                        or posixpath.basename(normalize_path(path).rstrip("/")))
            raw.append((_slug(str(entry.get("id") or label), "root"), label, path))
    ids = _unique([r[0] for r in raw])
    return [FsRoot(i, label, path) for i, (_, label, path) in zip(ids, raw)]


def resolve_path(p: Any, roots: list[FsRoot]) -> Any:
    """`hostfs://<id>/<rel>` -> the physical path, or None if it names no
    granted root or climbs out of one. Anything else passes through unchanged:
    a physical path typed by the human is still checked by the caller."""
    if not isinstance(p, str) or not p.startswith(SCHEME):
        return p
    rid, _, rel = p[len(SCHEME):].partition("/")
    root = next((r for r in roots if r.id == rid), None)
    if root is None:
        return None
    rel = rel.replace("\\", "/").strip("/")
    if ":" in rel:
        # A drive letter or an NTFS stream. Neither is a name inside a root.
        return None
    base = normalize_path(root.path)
    physical = normalize_path(base + "/" + rel) if rel else base
    return physical if under(base, physical) else None


def to_uri(physical: Any, roots: list[FsRoot]) -> str | None:
    """The logical name of a physical path, or None if no root contains it."""
    if not isinstance(physical, str):
        return None
    q = normalize_path(physical)
    for r in roots:
        base = normalize_path(r.path).rstrip("/")
        if q.lower() == base.lower():
            return r.uri
        if q.lower().startswith(base.lower() + "/"):
            return r.uri + "/" + q[len(base) + 1:]
    return None


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AppEntry:
    id: str
    label: str
    exe: str           # as granted: a bare name or a full path

    @property
    def canonical(self) -> str:
        return posixpath.basename(self.exe.replace("\\", "/"))


def app_entries(scope: Mapping[str, Any]) -> list[AppEntry]:
    raw = []
    for entry in scope.get("allowlist") or []:
        if isinstance(entry, str):
            exe = entry
            label = posixpath.splitext(posixpath.basename(exe.replace("\\", "/")))[0]
            raw.append((_slug(label, "app"), label, exe))
        elif isinstance(entry, Mapping) and isinstance(entry.get("exe"), str):
            exe = entry["exe"]
            label = str(entry.get("label") or posixpath.splitext(
                posixpath.basename(exe.replace("\\", "/")))[0])
            raw.append((_slug(str(entry.get("id") or label), "app"), label, exe))
    ids = _unique([r[0] for r in raw])
    return [AppEntry(i, label, exe) for i, (_, label, exe) in zip(ids, raw)]


def resolve_app(name: Any, apps: list[AppEntry]) -> AppEntry | None:
    """By id (exact), or by the executable as granted (case-insensitive).
    A label is for people; 'DOOM' is not 'doom'."""
    if not isinstance(name, str) or not name:
        return None
    for a in apps:
        if name == a.id:
            return a
    low = name.lower()
    for a in apps:
        if low in (a.exe.lower(), a.canonical.lower()):
            return a
    return None


# --------------------------------------------------------------------------
# The view that leaves the machine
# --------------------------------------------------------------------------

def logical_bounds(scopes: Mapping[str, Mapping[str, Any]]) -> dict[str, dict]:
    """Per capability, the resources a planner may name. No physical path."""
    out: dict[str, dict] = {}
    for cap, scope in scopes.items():
        view: dict[str, Any] = {}
        if "roots" in scope:
            view["roots"] = [{"id": r.id, "uri": r.uri, "label": r.label}
                             for r in fs_roots(scope)]
        if "allowlist" in scope:
            view["apps"] = [{"id": a.id, "label": a.label, "canonical": a.canonical}
                            for a in app_entries(scope)]
        if view:
            out[cap] = view
    return out
