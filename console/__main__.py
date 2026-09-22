"""IsyMotron console entry point. This is what the .exe runs.

    IsyMotron.exe                 # localhost only, opens the browser
    IsyMotron.exe --lan           # also reachable from a phone on the wifi
    IsyMotron.exe --port 9000
    IsyMotron.exe --no-browser

The console is a surface over the contract, not a new authority. It grants
nothing the CLI could not grant, refuses everything the CLI would refuse, and
every action it takes lands in the same sealed receipt ledger.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import webbrowser


def _bootstrap_paths() -> str:
    """Make the package importable whether frozen by PyInstaller or not."""
    if getattr(sys, "frozen", False):
        root = sys._MEIPASS                      # type: ignore[attr-defined]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for sub in ("", "core", "hosts", "tools"):
        p = os.path.join(root, sub) if sub else root
        if p not in sys.path:
            sys.path.insert(0, p)
    return root


ROOT = _bootstrap_paths()


def run_cli_verb(argv) -> "int | None":
    """If the first argument names a CLI verb, run the CLI instead of the
    console. Returns None when the arguments are the console's own.

    The frozen binary answers `IsyMotron.exe help` this way. Verbs that need the
    source checkout are refused by the CLI itself, out loud.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return None
    try:
        import isymotron_cli
    except ImportError:
        return None
    if args[0] not in isymotron_cli.VERBS:
        return None
    return isymotron_cli.main(args)

from console.server import (ConsoleState, lan_address, serve,  # noqa: E402
                            write_avatar_token)
from avatar.inbox import InboxTail, resolve_inbox_path, spawn_poller  # noqa: E402
from isymotron.awareness import HostAwarenessEngine           # noqa: E402
from relay.loopback import LoopbackRelay                      # noqa: E402

GREEN = "\033[38;2;118;185;0m"
DIM = "\033[38;2;120;120;128m"
OFF = "\033[0m"

BANNER = f"""{GREEN}
   ___ ___ _   _ __  __  ___ _____ ___  ___  _  _
  |_ _/ __| | | |  \\/  |/ _ \\_   _| _ \\/ _ \\| \\| |
   | |\\__ \\ |_| | |\\/| | (_) || | |   / (_) | .` |
  |___|___/\\__, |_|  |_|\\___/ |_| |_|_\\\\___/|_|\\_|
           |___/{OFF}  {DIM}capability fabric console{OFF}
"""


def build_world(args):
    """Attach the real host, plus a fixture if asked for a second one."""
    relay = LoopbackRelay()
    awareness = None
    grants_path = args.grants

    if sys.platform == "win32":
        from windows.grants import DEFAULT_PATH, Grants
        from windows.power import WindowsPowerProvider
        from windows.win11 import Win11Host

        grants_path = grants_path or DEFAULT_PATH
        host = Win11Host(Grants.load(grants_path))
        relay.attach(host)
        awareness = HostAwarenessEngine(host.identify().host_id,
                                        WindowsPowerProvider())
    else:
        print(f"note: no real host engine for {sys.platform}; "
              f"running with fixtures only.")

    if args.demo_host:
        from simulator.engines import LegacyHost
        relay.attach(LegacyHost(
            fs={"C:/NEMO/INBOX/.keep": "", "C:/GAMES/DOOM/DOOM.EXE": "MZ"},
            granted=["filesystem.read", "filesystem.write", "apps.launch",
                     "system.info"],
            grant_scopes={
                "filesystem.read": {"roots": ["C:/GAMES"]},
                "filesystem.write": {"roots": ["C:/NEMO/INBOX"]},
                "apps.launch": {"allowlist": ["DOOM.EXE"]},
                "system.info": {},
            }))
    return relay, awareness, grants_path


def provider_factory(awareness):
    """A model provider, or None when no key is configured.

    Returning None is deliberate: the console must be fully usable with no
    model at all. Devices, authority and receipts are the product; the planner
    is a consumer of it.
    """
    from agents.provider import Provider, ProviderError
    try:
        probe = Provider(awareness=awareness)
    except ProviderError:
        return None
    if not probe.configured():
        return None
    return lambda: Provider(awareness=awareness)


def main(argv=None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)

    dispatched = run_cli_verb(args_list)
    if dispatched is not None:
        return dispatched

    ap = argparse.ArgumentParser(prog="IsyMotron")
    ap.add_argument("--port", type=int, default=8760)
    ap.add_argument("--lan", action="store_true",
                    help="also serve on the local network (grants stay local-only)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--grants", default=None, help="path to the grant file")
    ap.add_argument("--demo-host", action="store_true",
                    help="attach a simulated legacy host alongside the real one")
    ap.add_argument("--avatar", action="store_true",
                    help="also launch the floating desktop avatar (subprocess)")
    ap.add_argument("--avatar-worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--url-file",
                    help="write the console URL here once serving (for scripts)")
    args = ap.parse_args(args_list)

    if args.avatar_worker:
        # The avatar runs in its own process: Tk wants the main thread, and a
        # dead pet must never take the console down (or vice versa).
        from avatar.window import run_avatar_worker
        return run_avatar_worker(port=args.port)

    print(BANNER)
    relay, awareness, grants_path = build_world(args)

    hosts = relay.hosts()
    if not hosts:
        print("  No host could be attached. Nothing to serve.")
        return 2
    for h in hosts:
        desc = relay.describe(h["host_id"])
        n, total = len(desc["granted"]), len(desc["capabilities"])
        state = f"{GREEN}{n}/{total} granted{OFF}" if n else f"{DIM}inert{OFF}"
        print(f"  host   {h['host_id']:<18} {h['engine']:<18} {state}")

    factory = provider_factory(awareness)
    print(f"  model  {'configured' if factory else DIM + 'none (set NVIDIA_NIM_API_KEY or NEBIUS_API_KEY)' + OFF}")
    print(f"  grants {grants_path}")

    state = ConsoleState(relay, awareness, grants_path, factory)

    # The authority channel (AV3). The `mode` event is emitted by
    # ConsoleState itself (AV6); here: the open channel reader as a daemon
    # thread, and the avatar token to a file only local processes read --
    # never argv, never a printed URL (R5).
    inbox_path = resolve_inbox_path()
    spawn_poller(InboxTail(state.avatar, inbox_path))
    print(f"  {DIM}avatar inbox {inbox_path}{OFF}")

    try:
        token_path = write_avatar_token(state.avatar_token)
        print(f"  {DIM}avatar token {token_path}{OFF}")
    except OSError as exc:
        print(f"  {DIM}avatar token not written: {exc}{OFF}")

    if args.avatar:
        # A separate process, so closing the pet does not stop the console
        # and vice versa. The pet reads the avatar token file (AV3); no token
        # travels on the command line.
        worker = ([sys.executable, "--avatar-worker", "--port", str(args.port)]
                  if getattr(sys, "frozen", False)
                  else [sys.executable, "-m", "console", "--avatar-worker",
                        "--port", str(args.port)])
        try:
            subprocess.Popen(worker, cwd=ROOT)
        except OSError as exc:
            print(f"  {DIM}avatar could not be launched: {exc}{OFF}")

    try:
        httpd, url = serve(state, port=args.port, lan=args.lan)
    except OSError as exc:
        print(f"\n  Could not bind port {args.port}: {exc}")
        print(f"  Try --port {args.port + 1}")
        return 1

    print()
    print(f"  {GREEN}console{OFF}  {url}")
    if args.lan:
        print(f"  {DIM}reachable from this network. Grants are refused from")
        print(f"  anywhere but this machine -- a remote surface uses authority,")
        print(f"  it never widens it.{OFF}")
    else:
        print(f"  {DIM}localhost only. Use --lan to open it on your phone.{OFF}")
    print(f"\n  {DIM}Ctrl-C to stop.{OFF}\n")

    if args.url_file:
        # A file, not a --token flag: a token on the command line is visible to
        # anything that can list processes, which is everything.
        with open(args.url_file, "w", encoding="utf-8") as fh:
            fh.write(url)

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
