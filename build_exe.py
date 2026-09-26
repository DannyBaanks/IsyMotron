"""Build the IsyMotron binary for Windows, Linux or macOS.

    python build_exe.py            # one file:   dist/IsyMotron.exe | dist/IsyMotron
    python build_exe.py --dir      # one folder, starts faster

PyInstaller is a *build-time* dependency only (requirements-build.txt). The
shipped binary carries the standard library and this repository, nothing
else: the runtime imports no third-party package, and
tests/test_png_codec.py::test_runtime_imports_no_third_party_package keeps that
claim executable rather than aspirational. (It was briefly false: the avatar
PNG codec leaned on Pillow until it was replaced by a stdlib zlib codec.)

A binary that builds and starts is NOT a supported host. The smoke test below
records the states separately (BUILDABLE, STARTABLE, HOST_SUPPORTED, ...) in
dist/smoke-<platform>.json. Windows and Linux attach a real host engine (M2);
macOS binaries start with simulated fixtures (--demo-host) and are
NOT_DEMONSTRATED as real hosts. See docs/PLATFORM_SUPPORT.md.

Windows 7 and earlier are out of scope for the product, not out of reach for
the contract. The reason is licensing: we cannot obtain legal copies of those
releases to test on, and an untested host would have to be marked
NOT_DEMONSTRATED anyway. Roadmap invariant 2.13 -- unsupported != impossible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ";" if os.name == "nt" else ":"
WINDOWS = sys.platform == "win32"
PLATFORM = {"win32": "windows", "linux": "linux", "darwin": "macos"}.get(
    sys.platform, sys.platform)
BINARY = "IsyMotron.exe" if WINDOWS else "IsyMotron"

#: Host engines that are real backends acting on this machine, by platform.
#: Everything else a binary attaches (nt-modern, dos-bridge, ...) is a
#: simulated fixture. The table is hosts/native.py's, so the build cannot
#: disagree with the runtime about which OS has a real host.
sys.path.insert(0, os.path.join(ROOT, "hosts"))
from native import REAL_ENGINES as _NATIVE  # noqa: E402

REAL_ENGINES = {{"win32": "windows"}.get(k, k): (v,) for k, v in _NATIVE.items()}

#: What the console prints when no real host backend exists for the platform.
#: The smoke test requires it verbatim, so the warning cannot quietly vanish.
NO_REAL_HOST_MARK = "NOT_DEMONSTRATED: no real host backend"

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
    "isymotron.seal", "isymotron.verify", "isymotron.process",
    "windows.win11", "windows.grants", "windows.power",
    "linux.host", "linux.power", "native",
    "simulator.engines",
    "agents.provider", "agents.planner", "agents.executor",
    "relay.loopback", "clients.fake_mobile",
    "console.server",
    "avatar.model", "avatar.protocol", "avatar.inbox",
    "avatar.pack", "avatar.window",
    # The command surface is imported by console/__main__.py so the frozen
    # binary answers `IsyMotron.exe help` too.
    "isymotron_cli",
]


def _stop(proc: subprocess.Popen) -> None:
    """Stop the binary AND its child.

    A one-file binary is a bootloader plus a child. `terminate()` kills the
    bootloader and can leave the child serving the port forever -- measured
    twice on Windows on 2026-09-18, both times locking the next build with
    PermissionError on dist/IsyMotron.exe. So kill the TREE: taskkill /T on
    Windows, the process group (start_new_session) on POSIX.

    Order matters on Windows: taskkill /T walks the tree from a LIVE parent.
    Terminating the bootloader first (the old order) left nothing to walk, and
    the child survived holding the smoke log open -- CI run 36179232526 had to
    reap it as an orphan.
    """
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def smoke_test(exe: str) -> "dict | None":
    """Start the binary, confirm it serves, stop it. Returns a receipt or None.

    Non-negotiable. The first build of this exe compiled without a warning and
    died on launch, because an over-eager --exclude-module dropped `email`,
    which the standard library's own `http.server` imports.

    The URL comes from a file rather than from the child's stdout: a frozen
    binary buffers stdout when it is a pipe, so reading its output blocks until
    the process exits -- which it never does, because it is a server. The
    second version of this function hung for seven minutes proving that.
    Stdout goes to a log file instead, read only after the binary is stopped.

    Off Windows there is no real host, so the binary is started with
    --demo-host (simulated fixtures) and must print NO_REAL_HOST_MARK.
    """
    import tempfile
    import urllib.error
    import urllib.request

    print(os.linesep + "  smoke test...")
    checks: list = []

    def ok(name: str) -> None:
        checks.append(name)
        print(f"  ok  {name}")

    def fail(msg: str) -> None:
        print(f"  FAILED: {msg}")

    argv = [exe, "--no-browser", "--port", "8799"]
    if PLATFORM not in REAL_ENGINES:
        argv.append("--demo-host")
    with tempfile.TemporaryDirectory() as tmp:
        url_file = os.path.join(tmp, "url.txt")
        log_path = os.path.join(tmp, "stdout.log")
        engines: list = []
        base = ""
        log_fh = open(log_path, "wb")
        popen_kw = {} if WINDOWS else {"start_new_session": True}
        proc = subprocess.Popen(argv + ["--url-file", url_file],
                                stdout=log_fh, stderr=subprocess.STDOUT,
                                **popen_kw)
        try:
            deadline = time.time() + 60
            url = ""
            while time.time() < deadline:
                if proc.poll() is not None:
                    fail(f"the binary exited with code {proc.returncode} before serving")
                    return None
                if os.path.exists(url_file):
                    url = open(url_file, encoding="utf-8").read().strip()
                    if url:
                        break
                time.sleep(0.4)
            if not url:
                fail("the binary never reported a console URL")
                return None
            ok("starts and reports a console URL")

            api = url.replace("/?t=", "/api/state?t=")
            with urllib.request.urlopen(api, timeout=15) as r:
                state = json.load(r)
            engines = [h["identity"]["engine"] for h in state.get("hosts", [])]
            if not engines:
                fail("/api/state lists no host")
                return None
            ok(f"serves /api/state, host engines {engines}")

            # And the surface is closed without one.
            try:
                urllib.request.urlopen(url.split("?")[0] + "api/state", timeout=10)
                fail("/api/state answered without a token")
                return None
            except urllib.error.HTTPError as exc:
                if exc.code != 401:
                    fail(f"expected 401 without a token, got {exc.code}")
                    return None
            ok("refuses /api/state without a token (401)")

            # Bundled data files, not just imports: a build that forgot
            # --add-data still starts and still serves the API.
            base = url.split("?")[0]
            for rel in ("", "app.js", "avatar/packs/malbolge-cat/manifest.json"):
                with urllib.request.urlopen(base + rel, timeout=10) as r:
                    if r.status != 200 or not r.read():
                        fail(f"bundled resource /{rel} is empty")
                        return None
            ok("serves bundled static files and the avatar pack")

            # The command surface must answer from the frozen binary too.
            cli = subprocess.run([exe, "help"], capture_output=True, text=True,
                                 timeout=60)
            if cli.returncode != 0 or "Usage: isymotron" not in cli.stdout:
                fail(f"`help` did not answer from the binary (exit {cli.returncode})")
                return None
            ok("answers `help` from the frozen binary")
        except (OSError, ValueError, KeyError) as exc:
            fail(f"{type(exc).__name__}: {exc}")
            return None
        finally:
            _stop(proc)
            log_fh.close()
        if proc.poll() is None:
            fail("the binary survived being stopped")
            return None
        # The bootloader exiting proves nothing about its child: the port
        # must stop answering too, or a one-file child is still serving.
        released = False
        for _ in range(20):
            try:
                urllib.request.urlopen(base, timeout=1).close()
            except (urllib.error.URLError, OSError):
                released = True
                break
            time.sleep(0.5)
        if not released:
            fail("the port still answers after stop: an orphaned child is serving")
            return None
        ok("stops when the harness stops it (process gone, port released)")
        log = open(log_path, "rb").read().decode("utf-8", "replace")

    real_prefixes = REAL_ENGINES.get(PLATFORM, ())
    real = [e for e in engines if e.startswith(real_prefixes)] if real_prefixes else []
    if real_prefixes and not real:
        fail(f"{PLATFORM} must attach a real host engine {real_prefixes}; got {engines}")
        return None
    if not real_prefixes:
        if NO_REAL_HOST_MARK not in log:
            fail(f"no real host on {PLATFORM}, but the binary did not say so "
                 f"({NO_REAL_HOST_MARK!r} missing from its output)")
            return None
        ok(f"says out loud that no real host backend is active on {PLATFORM}")

    receipt = {
        "schema": "isymotron-smoke/1",
        "platform": PLATFORM,
        "machine": platform.machine(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "binary": os.path.basename(exe),
        "sha256": _sha256(exe),
        "bytes": os.path.getsize(exe),
        "argv": [os.path.basename(argv[0])] + argv[1:],
        "host_engines": engines,
        "real_host_engines": real,
        "checks": checks,
        # Kept apart on purpose: a binary that starts is not a host.
        "states": {
            "BUILDABLE": "DEMONSTRATED",
            "PACKAGED": "NOT_DEMONSTRATED (the release workflow packages and hashes)",
            "STARTABLE": "DEMONSTRATED",
            "HOST_SUPPORTED": ("INFERRED (real engine attached; operations are "
                               "proven by the platform's host tests, not here)"
                               if real else
                               "NOT_DEMONSTRATED (simulated fixtures only)"),
            # Windows is the reference; any other real engine earns parity
            # from tests/test_host_parity.py on its own CI runner, never here.
            "PARITY_DEMONSTRATED": (
                "REFERENCE PLATFORM" if real and PLATFORM == "windows" else
                "INFERRED (proven by tests/test_host_parity.py on this OS, not here)"
                if real else "NOT_DEMONSTRATED"),
        },
    }
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="store_true",
                    help="one-folder build (starts faster, many files)")
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args(argv)

    if PLATFORM not in ("windows", "linux", "macos"):
        print(f"No build target for {sys.platform}.")
        return 2
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is missing.  python -m pip install -r requirements-build.txt")
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
        "--paths", os.path.join(ROOT, "tools"),
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

    # The .ico is Windows-only; PyInstaller would need Pillow to convert it
    # for macOS, and Linux binaries carry no icon.
    if not WINDOWS or not os.path.exists(cmd[cmd.index("--icon") + 1]):
        del cmd[cmd.index("--icon") + 1]
        cmd.remove("--icon")

    print("  building...")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    exe = os.path.join(ROOT, "dist",
                       BINARY if not args.dir else f"IsyMotron/{BINARY}")
    if not os.path.exists(exe):
        print("  PyInstaller reported success but produced no binary")
        return 1

    size = os.path.getsize(exe) / 1e6
    print(f"\n  {exe}")
    print(f"  {size:.1f} MB, built in {time.time() - t0:.0f}s")

    receipt = smoke_test(exe)
    if receipt is None:
        print("\n  BUILD REJECTED: the binary does not run.")
        return 1
    out = os.path.join(ROOT, "dist", f"smoke-{PLATFORM}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
        fh.write("\n")
    print(f"\n  smoke receipt {out}")
    for k, v in receipt["states"].items():
        print(f"    {k:<20} {v}")

    if WINDOWS:
        print("\n  Unsigned. Windows SmartScreen will warn on first run;")
        print("  that is expected for an unsigned binary and worth saying out")
        print("  loud rather than letting a judge discover it.")
    elif PLATFORM == "macos":
        print("\n  Unsigned and not notarized. Gatekeeper blocks a downloaded")
        print("  copy until the quarantine flag is cleared (docs/PLATFORM_SUPPORT.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
