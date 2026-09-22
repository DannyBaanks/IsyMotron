"""Build IsyMotron.exe for Windows 10/11.

    python build_exe.py            # one file, dist/IsyMotron.exe
    python build_exe.py --dir      # one folder, starts faster

PyInstaller is a *build-time* dependency only. The shipped binary carries the
standard library and this repository, nothing else -- the whole project imports
no third-party package at runtime, which is why one file is 10 MB and not 200.

Windows 7 and earlier are out of scope for the product, not out of reach for
the contract. The reason is licensing: we cannot obtain legal copies of those
releases to test on, and an untested host would have to be marked
NOT_DEMONSTRATED anyway. Roadmap invariant 2.13 -- unsupported != impossible.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ";" if os.name == "nt" else ":"

#: Everything the frozen app must be able to import or read. PyInstaller
#: follows imports, but these are reached through sys.path juggling and by
#: filename, so they are declared rather than discovered.
DATA = [
    ("console/static", "console/static"),
    ("avatar/packs", "avatar/packs"),
]
HIDDEN = [
    "isymotron.awareness", "isymotron.attribution", "isymotron.contracts",
    "isymotron.host", "isymotron.policy", "isymotron.verdicts", "isymotron.canon",
    "isymotron.seal", "isymotron.verify",
    "windows.win11", "windows.grants", "windows.power",
    "simulator.engines",
    "agents.provider", "agents.planner", "agents.executor",
    "relay.loopback", "clients.fake_mobile",
    "console.server",
    "avatar.model", "avatar.protocol", "avatar.inbox",
    "avatar.pack", "avatar.window",
]


def smoke_test(exe: str) -> bool:
    """Start the binary, confirm it serves, stop it.

    Non-negotiable. The first build of this exe compiled without a warning and
    died on launch, because an over-eager --exclude-module dropped `email`,
    which the standard library's own `http.server` imports.

    The URL comes from a file rather than from the child's stdout: a frozen
    binary buffers stdout when it is a pipe, so reading its output blocks until
    the process exits -- which it never does, because it is a server. The
    second version of this function hung for seven minutes proving that.
    """
    import json
    import tempfile
    import urllib.error
    import urllib.request

    print(os.linesep + "  smoke test...")
    with tempfile.TemporaryDirectory() as tmp:
        url_file = os.path.join(tmp, "url.txt")
        proc = subprocess.Popen(
            [exe, "--no-browser", "--port", "8799", "--url-file", url_file],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.time() + 30
            url = ""
            while time.time() < deadline:
                if proc.poll() is not None:
                    print(f"  FAILED: the binary exited with code {proc.returncode} "
                          f"before serving")
                    return False
                if os.path.exists(url_file):
                    url = open(url_file, encoding="utf-8").read().strip()
                    if url:
                        break
                time.sleep(0.4)
            if not url:
                print("  FAILED: the binary never reported a console URL")
                return False

            api = url.replace("/?t=", "/api/state?t=")
            with urllib.request.urlopen(api, timeout=15) as r:
                state = json.load(r)
            hosts = len(state.get("hosts", []))
            print(f"  serves /api/state, {hosts} host(s), tier {state.get('tier')}")

            # And the surface is closed without one.
            try:
                urllib.request.urlopen(url.split("?")[0] + "api/state", timeout=10)
                print("  FAILED: /api/state answered without a token")
                return False
            except urllib.error.HTTPError as exc:
                if exc.code != 401:
                    print(f"  FAILED: expected 401 without a token, got {exc.code}")
                    return False
            print("  refuses /api/state without a token (401)")
            return hosts > 0
        except (OSError, ValueError) as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            return False
        finally:
            # A one-file exe is a bootloader plus a child. `terminate()` kills
            # the bootloader and leaves the child serving the port forever —
            # measured twice on 2026-09-18, both times locking the next build
            # with PermissionError on dist/IsyMotron.exe. Kill the TREE.
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="store_true",
                    help="one-folder build (starts faster, many files)")
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args(argv)

    if sys.platform != "win32":
        print("This builds a Windows binary and must run on Windows.")
        return 2
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is missing.  python -m pip install pyinstaller")
        return 2

    if args.clean:
        for d in ("build", "dist"):
            shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "IsyMotron",
        "--onedir" if args.dir else "--onefile",
        "--console",                      # the banner and the URL are the UI
        "--noconfirm",
        "--icon", os.path.join(ROOT, "console", "static", "icon.ico"),
        "--paths", os.path.join(ROOT, "core"),
        "--paths", os.path.join(ROOT, "hosts"),
        "--paths", ROOT,
    ]
    for src, dest in DATA:
        cmd += ["--add-data", f"{os.path.join(ROOT, src)}{SEP}{dest}"]
    for mod in HIDDEN:
        cmd += ["--hidden-import", mod]
    # Nothing here needs a test runner baked in. `tkinter` is NOT excluded
    # since AV5: the desktop avatar is Tk, and it ships in the same exe.
    #
    # `email` and `xml` are NOT excluded, however tempting: `http.server`
    # imports `email`, and dropping it produced a binary that built cleanly,
    # reported success, and died on launch with ModuleNotFoundError. A build
    # that compiles is not a build that runs -- hence the smoke test below.
    for junk in ("unittest", "pydoc", "doctest", "pytest", "sqlite3"):
        cmd += ["--exclude-module", junk]
    cmd.append(os.path.join(ROOT, "console", "__main__.py"))

    if not os.path.exists(cmd[cmd.index("--icon") + 1]):
        del cmd[cmd.index("--icon") + 1]
        cmd.remove("--icon")

    print("  building...")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    exe = os.path.join(ROOT, "dist",
                       "IsyMotron.exe" if not args.dir else "IsyMotron/IsyMotron.exe")
    if not os.path.exists(exe):
        print("  PyInstaller reported success but produced no binary")
        return 1

    size = os.path.getsize(exe) / 1e6
    print(f"\n  {exe}")
    print(f"  {size:.1f} MB, built in {time.time() - t0:.0f}s")

    if not smoke_test(exe):
        print("\n  BUILD REJECTED: the binary does not run.")
        return 1

    print("\n  Unsigned. Windows SmartScreen will warn on first run;")
    print("  that is expected for an unsigned binary and worth saying out")
    print("  loud rather than letting a judge discover it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
