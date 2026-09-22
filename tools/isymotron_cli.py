"""isymotron — one command for the whole product.

**M0 of `.opencode/plans/isymotron-cli-completo.md`: the verb table and the
machinery that proves it is complete.** Dispatch, help, the interactive menu
and key management land in later milestones; nothing here executes yet.

This module is the single source of truth for the CLI surface. The previous
CLI (`isymotron.ps1`) kept its verbs in two places -- the help table and the
dispatch chain -- and documented the consequence itself: *"keep the two lists
in sync or the CLI rots"*. Here there is one table, and a test that goes red
when an entrypoint is left orphaned.

Invariant inherited from `isymotron.ps1`: **the CLI holds no authority of its
own.** Every verb is a pass-through to a command that already exists; granting
still goes through `tools/host_cli.py` or the loopback console, and the CLI
never widens a grant or mints a receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Verb:
    """One user-facing command and the entrypoint it passes through to."""

    name: str
    summary: str
    #: argv prefix for the pass-through (M1/M2 dispatch uses it).
    argv: tuple[str, ...] = ()
    #: a path (`tools/host_cli.py`) or a module invocation (`-m console`).
    #: `None` means the verb is implemented inside the CLI itself.
    entrypoint: str | None = None
    #: subcommand name -> entrypoint, for grouped verbs (`quine demo`).
    subcommands: Mapping[str, str] = field(default_factory=dict)
    #: reserved for the interactive menu gate (M5); no verb needs a TTY today,
    #: because every action is also reachable as a plain subcommand.
    needs_tty: bool = False

    def referenced_entrypoints(self) -> set[str]:
        refs: set[str] = set()
        if self.entrypoint:
            refs.add(self.entrypoint)
        refs.update(self.subcommands.values())
        return refs


#: The one table. Order is the order the help prints.
VERBS: dict[str, Verb] = {
    # -- verbs that already existed in isymotron.ps1 ------------------------
    "start": Verb(
        name="start",
        summary="console + floating pet + browser (adds --avatar)",
        argv=("-m", "console", "--avatar"),
        entrypoint="-m console",
    ),
    "console": Verb(
        name="console",
        summary="the local web console (--lan --demo-host --port N ...)",
        argv=("-m", "console"),
        entrypoint="-m console",
    ),
    "pet": Verb(
        name="pet",
        summary="only the floating desktop pet (idles alone; follows the console)",
        argv=("-m", "console", "--avatar-worker", "--port", "8760"),
        entrypoint="-m console",
    ),
    "test": Verb(
        name="test",
        summary="the acceptance suite (default: -q)",
        argv=("-m", "pytest", "-q"),
        entrypoint="-m pytest",
    ),
    "build": Verb(
        name="build",
        summary="rebuild IsyMotron.exe (smoke test included)",
        argv=("build_exe.py",),
        entrypoint="build_exe.py",
    ),
    "spoof": Verb(
        name="spoof",
        summary="append the hostile demo lines to an inbox",
        argv=("tools/avatar_spoof.py",),
        entrypoint="tools/avatar_spoof.py",
    ),
    "host": Verb(
        name="host",
        summary="status | grant | revoke | do (the local human, via host_cli.py)",
        argv=("tools/host_cli.py",),
        entrypoint="tools/host_cli.py",
    ),
    "demo": Verb(
        name="demo",
        summary="the M0 walkthrough (writes evidence/M0/)",
        argv=("tools/m0_demo.py",),
        entrypoint="tools/m0_demo.py",
    ),
    "learn": Verb(
        name="learn",
        summary="a verified lesson from a learning pack (malbolge)",
        argv=("-m", "learning"),
        entrypoint="-m learning",
    ),
    "install": Verb(
        name="install",
        summary="make `isymotron` work from any new shell",
    ),
    "where": Verb(
        name="where",
        summary="print the repository this CLI belongs to",
    ),
    "help": Verb(
        name="help",
        summary="this help",
    ),
    # -- verbs added by the CLI plan ---------------------------------------
    "keys": Verb(
        name="keys",
        summary="set | list | unset | check API keys and secrets (never echoed)",
    ),
    "quine": Verb(
        name="quine",
        summary="Quine Gate: demo | verify | publish",
        subcommands={
            "demo": "tools/quine_gate_demo.py",
            "verify": "tools/quine_gate_verify.py",
            "publish": "tools/quine_gate_publish.py",
        },
    ),
    "process": Verb(
        name="process",
        summary="Process Verifier: observe | store | verify (exit 0/1/2)",
        argv=("tools/process_verify.py",),
        entrypoint="tools/process_verify.py",
    ),
    "evidence": Verb(
        name="evidence",
        summary="verify a hashes.json manifest against the bytes on disk",
        entrypoint="core/isymotron/evidence.py",
    ),
    "nemotron": Verb(
        name="nemotron",
        summary="probe the provider seam (--provider nebius|nvidia, --models)",
        argv=("tools/nemotron_check.py",),
        entrypoint="tools/nemotron_check.py",
    ),
    "host-watch": Verb(
        name="host-watch",
        summary="watch host awareness over time (--seconds, --tick, --probe)",
        argv=("tools/host_watch.py",),
        entrypoint="tools/host_watch.py",
    ),
}


#: `-m` entrypoints that exist as importable packages.
MODULE_ENTRYPOINTS: tuple[str, ...] = ("-m console", "-m learning", "-m pytest")

#: scripts at the repository root that the CLI wraps.
ROOT_SCRIPTS: tuple[str, ...] = ("build_exe.py",)

#: Files that are deliberately NOT verbs, each with a reason. Excluding
#: something here is a decision on the record, not silence.
EXCLUDED: dict[str, str] = {
    "tools/isymotron_cli.py":
        "the CLI itself: it is the surface, not a wrapped entrypoint",
    "core/isymotron/doctor.py":
        "library, no CLI entrypoint yet (plan M4/M8 keeps it NOT_DEMONSTRATED)",
    "core/isymotron/marketplace.py":
        "library, no CLI entrypoint yet (plan M4/M8 keeps it NOT_DEMONSTRATED)",
}


def known_entrypoints(root: Path = REPO) -> set[str]:
    """Every entrypoint that exists on disk and should be reachable, or be
    explicitly excluded."""
    tools = {f"tools/{path.name}" for path in (root / "tools").glob("*.py")}
    return tools | set(MODULE_ENTRYPOINTS) | set(ROOT_SCRIPTS)


def referenced_entrypoints(verbs: Mapping[str, Verb] | None = None) -> set[str]:
    verbs = VERBS if verbs is None else verbs
    refs: set[str] = set()
    for verb in verbs.values():
        refs |= verb.referenced_entrypoints()
    return refs


def orphan_entrypoints(verbs: Mapping[str, Verb] | None = None,
                       root: Path = REPO) -> list[str]:
    """Entrypoints that exist but no verb reaches and no exclusion covers.

    Non-empty means the CLI surface has rotted: a capability exists and cannot
    be reached from the one command that is supposed to reach everything.
    """
    return sorted(known_entrypoints(root) - referenced_entrypoints(verbs) - set(EXCLUDED))
