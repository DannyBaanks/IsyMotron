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

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

REPO = Path(__file__).resolve().parent.parent

# Import the in-repo library the same way every other tools/*.py does.
for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


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
        argv=("-m", "pytest"),
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


# ─── style (parity with isymotron.ps1:33-48) ────────────────────────────────

_ANSI = {
    "reset": "\x1b[0m", "bold": "\x1b[1m", "dim": "\x1b[2m",
    "brand": "\x1b[38;2;118;185;0m",      # #76B900
    "accent": "\x1b[38;2;145;199;51m",    # #91C733
    "red": "\x1b[1;38;2;254;63;63m",      # rustc error red
}


def _use_colour(stream=None) -> bool:
    """Colour only where a human reads it: interactive, and not switched off."""
    stream = sys.stdout if stream is None else stream
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _style(text: str, *codes: str, stream=None) -> str:
    if not _use_colour(stream) or not codes:
        return text
    return "".join(_ANSI[c] for c in codes) + text + _ANSI["reset"]


def _is_tty() -> bool:
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


#: Static render of tools/cli-banner.gf (same art the PowerShell CLI carries).
BANNER = (
    " ### ##### #   # #   # ###### ##### ####  ###### #   #\n"
    "  #  #      # #  ## ## #    #   #   #  #  #    # #  ##\n"
    "  #  #####   #   # # # #    #   #   ####  #    # # # #\n"
    "  #      #   #   #   # #    #   #   #  #  #    # ##  #\n"
    " ### #####   #   #   # ######   #   #   # ###### #   #"
)

USAGE = "Usage: isymotron [OPTIONS] [COMMAND] [ARGS]..."


def print_banner() -> None:
    print()
    print(_style(BANNER, "brand"))
    print("  " + _style("capability fabric", "dim") + _style(
        " -- one command for the whole product", "bold"))
    print()


def print_help(*, long: bool = True) -> None:
    print(USAGE)
    print()
    print(_style("Commands:", "bold"))
    for verb in VERBS.values():
        print("  {:<12} {}".format(verb.name, verb.summary))
    print()
    print(_style("Options:", "bold"))
    print("  -h, --help      Print help")
    print("  -V, --version   Print version")
    if long:
        print()
        print(_style("Notes:", "bold"))
        print("  - Every command is a pass-through; this CLI holds no authority of")
        print("    its own. Granting goes through `isymotron host grant` or the console.")
        print("  - With no arguments and no terminal it prints this help and exits;")
        print("    it never waits for input that is not coming.")


def print_usage_error(message: str) -> None:
    print()
    print(_style("error:", "red", "bold") + " " + message)
    print()
    print(USAGE)
    print()
    print("For more information, try 'isymotron help'.")


def repo_version() -> str:
    try:
        done = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5)
        revision = done.stdout.strip()
    except Exception:
        revision = ""
    return f"isymotron 1.0.0 {revision}".strip()


def run_pass_through(argv_prefix, rest: list[str]) -> int:
    """Run an entrypoint with the caller's arguments forwarded verbatim, and
    propagate its exit code unchanged. Flags the subcommand understands reach
    it untouched; there is no `--` separator to remember because the top-level
    dispatch parses no flags at all."""
    try:
        return subprocess.run([sys.executable, *argv_prefix, *rest],
                              cwd=str(REPO), env=child_env()).returncode
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130
    except OSError as exc:
        print(_style("error:", "red", "bold")
              + f" could not run {' '.join(argv_prefix)}: {exc}")
        return 2


def run_entrypoint(verb: Verb, rest: list[str]) -> int:
    """Run a single-entrypoint verb."""
    return run_pass_through(verb.argv, verb_args(verb, rest))


#: Arguments added when the caller passes none. Parity with isymotron.ps1,
#: which runs `pytest -q` for a bare `test` and `host_cli.py status` for a bare
#: `host`.
DEFAULT_ARGS: dict[str, tuple[str, ...]] = {
    "test": ("-q",),
    "host": ("status",),
}


def verb_args(verb: Verb, rest: list[str]) -> list[str]:
    """The caller's arguments, or the verb's documented defaults."""
    return list(rest) if rest else list(DEFAULT_ARGS.get(verb.name, ()))


def build_argv(verb: Verb, rest: list[str], *,
               executable: str | None = None) -> list[str]:
    """The exact argv for a verb. Pure, so parity can be tested without
    running anything."""
    return [executable or sys.executable, *verb.argv, *verb_args(verb, rest)]


# ─── keys (M3): secrets live outside the repo and are never echoed ──────────

#: Values that must never be printed once stored.
SECRET_KEYS: tuple[str, ...] = (
    "NEBIUS_API_KEY", "NVIDIA_NIM_API_KEY", "ISYMOTRON_RECEIPT_KEY",
)
#: Non-secret configuration the same command manages.
CONFIG_KEYS: tuple[str, ...] = ("ISYMOTRON_PROVIDER",)
KNOWN_KEYS: tuple[str, ...] = SECRET_KEYS + CONFIG_KEYS
PROVIDER_VALUES: tuple[str, ...] = ("nvidia", "nebius")

STORE_ENV = "ISYMOTRON_KEY_STORE"


def default_store_path() -> Path:
    """The store lives outside the repository, per platform.

    One file on every platform (not the registry): a single auditable store,
    no registry mutation, and the CLI injects it into every child it runs, so
    nothing else needs to see it.
    """
    override = os.environ.get(STORE_ENV)
    if override:
        return Path(override)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "isymotron" / "keys.env"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "isymotron" / "keys.env"


def load_store(path: Path | None = None) -> dict[str, str]:
    target = path or default_store_path()
    values: dict[str, str] = {}
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


def save_store(values: dict[str, str], path: Path | None = None) -> Path:
    target = (path or default_store_path()).resolve()
    if REPO.resolve() in target.parents:
        raise ValueError(
            f"refusing to write secrets inside the repository ({target}); "
            f"set {STORE_ENV} elsewhere")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    body = "".join(f"{name}={values[name]}\n" for name in sorted(values))
    # Atomic: a reader never sees a half-written store. newline="\n" so the
    # store is byte-stable across platforms.
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, target)
    return target


def fingerprint(value: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def child_env() -> dict[str, str]:
    """The environment every child of the CLI runs with: the process
    environment plus the stored keys, so the user never has to export."""
    env = dict(os.environ)
    env.update(load_store())
    return env


KEYS_USAGE = "usage: isymotron keys {list|set <NAME>|unset <NAME>|check [--live]}"


def _read_secret(name: str) -> str:
    """Hidden on a terminal; one line from stdin when it is piped (tests,
    automation). Never from argv, so a secret cannot land in shell history."""
    if _is_tty():
        import getpass
        return getpass.getpass(f"{name}: ")
    return sys.stdin.readline().rstrip("\n")


def _validate_value(name: str, value: str) -> str | None:
    if not value:
        return "empty value"
    if value != value.strip():
        return "value has leading or trailing whitespace"
    if name == "ISYMOTRON_PROVIDER" and value not in PROVIDER_VALUES:
        return f"{name} must be one of {', '.join(PROVIDER_VALUES)}"
    return None


def _keys_problem(message: str) -> int:
    print(_style("error:", "red", "bold") + f" {message}")
    print(KEYS_USAGE)
    return 2


def cmd_keys(rest: list[str]) -> int:
    action = rest[0] if rest else "list"
    args = rest[1:]
    store_path = default_store_path()

    if action == "list":
        values = load_store(store_path)
        print(f"store: {store_path}")
        for name in KNOWN_KEYS:
            value = values.get(name)
            if value is None:
                print(f"  {name:<24} missing")
            elif name in SECRET_KEYS:
                print(f"  {name:<24} set  {fingerprint(value)}")
            else:
                print(f"  {name:<24} set  {value}")
        return 0

    if action == "set":
        if not args:
            return _keys_problem("keys set needs a key name")
        name = args[0]
        if name not in KNOWN_KEYS:
            return _keys_problem(f"unknown key {name!r}; known: {', '.join(KNOWN_KEYS)}")
        value = _read_secret(name)
        problem = _validate_value(name, value)
        if problem:
            return _keys_problem(problem)
        values = load_store(store_path)
        values[name] = value
        try:
            target = save_store(values, store_path)
        except ValueError as exc:
            return _keys_problem(str(exc))
        shown = fingerprint(value) if name in SECRET_KEYS else value
        print(f"{name}: stored ({shown}) -> {target}")
        return 0

    if action == "unset":
        if not args:
            return _keys_problem("keys unset needs a key name")
        name = args[0]
        values = load_store(store_path)
        if name not in values:
            print(f"{name}: was not set")
            return 0
        del values[name]
        try:
            save_store(values, store_path)
        except ValueError as exc:
            return _keys_problem(str(exc))
        print(f"{name}: unset")
        return 0

    if action == "check":
        values = load_store(store_path)
        ok = True
        for name in KNOWN_KEYS:
            value = values.get(name)
            if value is None:
                print(f"  {name:<24} missing")
                ok = False
                continue
            problem = _validate_value(name, value)
            if problem:
                print(f"  {name:<24} invalid: {problem}")
                ok = False
            else:
                shown = fingerprint(value) if name in SECRET_KEYS else value
                print(f"  {name:<24} ok  {shown}")
        if "--live" in args:
            provider_key = values.get("NEBIUS_API_KEY") or values.get("NVIDIA_NIM_API_KEY")
            if not provider_key:
                return _keys_problem("--live needs a provider key stored first")
            print("running the provider probe with the stored key (live network call)")
            return run_entrypoint(VERBS["nemotron"], [])
        return 0 if ok else 2

    return _keys_problem(f"unknown keys action {action!r}")


EVIDENCE_USAGE = "usage: isymotron evidence verify <manifest.json>"


def cmd_evidence(rest: list[str]) -> int:
    """`evidence verify`: the manifest checker had no CLI until now."""
    if len(rest) != 2 or rest[0] != "verify":
        print(_style("error:", "red", "bold")
              + " evidence takes: verify <manifest.json>")
        print(EVIDENCE_USAGE)
        return 2
    from isymotron.evidence import verify_manifest
    result = verify_manifest(rest[1])
    print(json.dumps(result.to_dict(), indent=2))
    if result.passed:
        return 0
    # it ran and found a mismatch -> 1; it could not verify at all -> 2
    return 1 if result.artifacts else 2


def run_grouped(verb: Verb, rest: list[str]) -> int:
    if not rest:
        print_usage_error(
            f"'{verb.name}' needs a subcommand: {' | '.join(verb.subcommands)}")
        return 2
    sub, tail = rest[0], rest[1:]
    entry = verb.subcommands.get(sub)
    if entry is None:
        print_usage_error(
            f"unknown {verb.name} subcommand '{sub}': "
            + " | ".join(verb.subcommands))
        return 2
    return run_pass_through([entry], tail)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        # The interactive menu (M5) goes here when there is a terminal.
        print_help()
        return 0

    command, rest = args[0], args[1:]

    if command in ("help", "--help"):
        print_banner()
        print_help()
        return 0
    if command == "-h":
        print_help(long=False)
        return 0
    if command in ("-V", "--version", "version"):
        print(repo_version())
        return 0
    if command == "where":
        print(REPO)
        return 0
    if command == "keys":
        return cmd_keys(rest)
    if command == "install":
        # Deliberate fail-closed: a verb that exists in the table but has no
        # implementation yet must not look like it worked.
        print(_style("error:", "red", "bold")
              + " 'install' is not implemented in this build (plan milestone M6)")
        return 2

    if command == "evidence":
        return cmd_evidence(rest)

    verb = VERBS.get(command)
    if verb is None:
        print_usage_error(f"unknown command '{command}'")
        return 2
    if verb.subcommands:
        return run_grouped(verb, rest)
    if verb.entrypoint is None:
        print(_style("error:", "red", "bold") + f" '{command}' has no entrypoint wired yet")
        return 2
    return run_entrypoint(verb, rest)


if __name__ == "__main__":
    raise SystemExit(main())
