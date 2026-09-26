"""Grants path (XDG) + honest non-Windows host identity."""
import importlib
import os

import windows.grants as grants_mod
from windows.grants import Grants


def _reload():
    return importlib.reload(grants_mod)


def test_default_path_posix_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv("HOME", str(tmp_path))
    # expanduser reads USERPROFILE on a Windows runner, not HOME.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    mod = _reload()
    assert mod._default_path() == os.path.join(
        str(tmp_path), ".config", "isymotron", "grants.json"
    )


def test_default_path_respects_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv("HOME", str(tmp_path))
    # expanduser reads USERPROFILE on a Windows runner, not HOME.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    mod = _reload()
    assert mod._default_path() == os.path.join(
        str(tmp_path), "xdg", "isymotron", "grants.json"
    )


def test_default_path_legacy_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv("HOME", str(tmp_path))
    # expanduser reads USERPROFILE on a Windows runner, not HOME.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    legacy = tmp_path / "IsyMotron" / "grants.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}", encoding="utf-8")
    mod = _reload()
    assert mod._default_path() == str(legacy)


def test_default_path_windows_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    mod = _reload()
    assert mod._default_path().endswith("grants.json")
    assert "IsyMotron" in mod._default_path()


def test_posix_host_identity_is_honest():
    mod = _reload()
    if os.name == "nt":
        return
    host_id = mod._default_host_id()
    assert host_id.startswith("linux-") or host_id.startswith("darwin-"), host_id
    display = mod._default_display_name()
    assert "Windows" not in display, display


def test_load_missing_is_inert(tmp_path):
    grants = Grants.load(str(tmp_path / "nope.json"))
    assert grants.granted == []
    assert grants.source.startswith("<inert:")
