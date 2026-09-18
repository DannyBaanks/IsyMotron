"""Logical resources — the model names a resource, the host knows where it is.

The catalogue used to say "inside the granted roots" without saying which, so
a model could only succeed by guessing a path. Now every granted root and app
has a logical name (`hostfs://demo`, `doom`). The model plans against those
names; the host translates them to physical paths it never has to disclose.
See docs/FINDINGS.md #9.
"""
from __future__ import annotations

import json

import pytest

from agents.executor import Executor
from agents.planner import Planner
from agents.provider import ScriptedProvider
from isymotron.contracts import ExecutionRequest
from isymotron.resources import (
    app_entries,
    fs_roots,
    logical_bounds,
    resolve_app,
    resolve_path,
    to_uri,
)
from isymotron.verdicts import Decision, DenyReason
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost

PHOTOS = "C:/Users/someone/Pictures/Demo"


# -- naming -----------------------------------------------------------------

def test_a_plain_root_gets_a_name_from_its_folder():
    [r] = fs_roots({"roots": [PHOTOS]})
    assert (r.id, r.uri, r.label, r.path) == ("demo", "hostfs://demo", "Demo", PHOTOS)


def test_an_explicit_root_keeps_its_own_name():
    [r] = fs_roots({"roots": [{"id": "fotos", "label": "Mis fotos", "path": PHOTOS}]})
    assert (r.id, r.uri, r.label) == ("fotos", "hostfs://fotos", "Mis fotos")


def test_two_roots_with_the_same_folder_name_get_distinct_ids():
    roots = fs_roots({"roots": ["C:/a/Demo", "D:/b/Demo"]})
    assert [r.id for r in roots] == ["demo", "demo-2"]


def test_a_plain_app_gets_a_name_from_its_executable():
    [a] = app_entries({"allowlist": ["DOOM.EXE"]})
    assert (a.id, a.label, a.exe) == ("doom", "DOOM", "DOOM.EXE")


def test_an_app_given_by_full_path_is_named_by_its_file():
    [a] = app_entries({"allowlist": ["C:/Games/Doom/DOOM.EXE"]})
    assert a.id == "doom"


# -- what the model is allowed to see ---------------------------------------

def test_bounds_never_contain_a_physical_path():
    scopes = {
        "filesystem.read": {"roots": [PHOTOS]},
        "apps.launch": {"allowlist": ["C:/Games/Doom/DOOM.EXE"]},
    }
    view = logical_bounds(scopes)
    text = json.dumps(view)
    assert "someone" not in text and "C:" not in text and "Games" not in text
    assert view["filesystem.read"]["roots"] == [
        {"id": "demo", "uri": "hostfs://demo", "label": "Demo"}]
    assert view["apps.launch"]["apps"] == [
        {"id": "doom", "label": "DOOM", "canonical": "DOOM.EXE"}]


# -- translation ------------------------------------------------------------

@pytest.mark.parametrize("uri, physical", [
    ("hostfs://demo", PHOTOS),
    ("hostfs://demo/", PHOTOS),
    ("hostfs://demo/nota.txt", PHOTOS + "/nota.txt"),
    ("hostfs://demo/sub/x.png", PHOTOS + "/sub/x.png"),
])
def test_a_logical_path_translates_inside_its_root(uri, physical):
    assert resolve_path(uri, fs_roots({"roots": [PHOTOS]})) == physical


@pytest.mark.parametrize("uri", [
    "hostfs://demo/../../../Windows/System32",
    "hostfs://demo/..\\..\\secret.txt",
    "hostfs://demo/C:/Windows/win.ini",
    "hostfs://nope/x.txt",
    "hostfs://",
])
def test_a_logical_path_never_escapes_or_invents_a_root(uri):
    assert resolve_path(uri, fs_roots({"roots": [PHOTOS]})) is None


def test_a_physical_path_passes_through_for_the_human_at_the_keyboard():
    assert resolve_path("C:/x/y.txt", fs_roots({"roots": [PHOTOS]})) == "C:/x/y.txt"


def test_a_physical_path_maps_back_to_its_logical_name():
    roots = fs_roots({"roots": [PHOTOS]})
    assert to_uri(PHOTOS + "/nota.txt", roots) == "hostfs://demo/nota.txt"
    assert to_uri(PHOTOS.upper().replace("/", "\\"), roots) == "hostfs://demo"
    assert to_uri("C:/elsewhere/x", roots) is None


@pytest.mark.parametrize("asked, found", [
    ("doom", "DOOM.EXE"),
    ("DOOM.EXE", "DOOM.EXE"),
    ("doom.exe", "DOOM.EXE"),
    ("DOOM", None),          # a label is not an id
    ("C:/Games/DOOM.EXE", None),
    ("quake", None),
])
def test_an_app_resolves_by_id_or_canonical_name_only(asked, found):
    hit = resolve_app(asked, app_entries({"allowlist": ["DOOM.EXE"]}))
    assert (hit.exe if hit else None) == found


# -- through the enforcer and the engine ------------------------------------

@pytest.fixture
def world():
    modern = ModernHost(
        # The fixture FS stamps mtimes in name order, so b.png is the newest.
        fs={PHOTOS + "/a.png": "AAA", PHOTOS + "/b.png": "BBB"},
        granted=["filesystem.read", "system.info"],
        grant_scopes={"filesystem.read": {"roots": [PHOTOS]}, "system.info": {}},
    )
    legacy = LegacyHost(
        fs={"C:/NEMO/INBOX/.keep": ""},
        granted=["filesystem.write", "apps.launch"],
        grant_scopes={"filesystem.write": {"roots": ["C:/NEMO/INBOX"]},
                      "apps.launch": {"allowlist": ["DOOM.EXE"]}},
    )
    relay = LoopbackRelay()
    relay.attach(modern)
    relay.attach(legacy)
    return relay, modern, legacy


def act(host, capability, **params):
    lease, _ = host.request_lease("test", capability, 60)
    req = ExecutionRequest.make(host.identify().host_id, "test", capability,
                                params, lease.lease_id)
    return host.execute_capability(req)


def test_the_host_reads_through_a_logical_path(world):
    _, modern, _ = world
    r = act(modern, "filesystem.read", path="hostfs://demo/a.png")
    assert r.decision.decision is Decision.ALLOW
    assert r.result["text"] == "AAA"
    assert r.result["path"] == "hostfs://demo/a.png"


def test_an_unknown_root_is_denied_with_a_receipt(world):
    _, modern, _ = world
    r = act(modern, "filesystem.read", path="hostfs://secrets/x")
    assert r.decision.decision is Decision.DENY
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert r.verify()


def test_an_escape_through_a_logical_path_is_denied(world):
    _, modern, _ = world
    r = act(modern, "filesystem.read", path="hostfs://demo/../../../Windows")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE


def test_a_listing_names_its_newest_file_logically(world):
    _, modern, _ = world
    r = act(modern, "filesystem.read", path="hostfs://demo")
    assert r.result["path"] == "hostfs://demo"
    assert [e["uri"] for e in r.result["entries"]] == [
        "hostfs://demo/b.png", "hostfs://demo/a.png"]
    assert r.result["newest"] == r.result["entries"][0]["uri"]


def test_an_app_launches_by_id_and_the_label_is_refused(world):
    _, _, legacy = world
    ok = act(legacy, "apps.launch", app="doom")
    assert ok.decision.decision is Decision.ALLOW
    assert legacy.launched == ["DOOM.EXE"]
    no = act(legacy, "apps.launch", app="DOOM")
    assert no.decision.reason is DenyReason.OUT_OF_SCOPE


# -- the planner sees names, never places -----------------------------------

def test_the_catalogue_shows_logical_bounds_and_no_physical_path(world):
    relay, modern, legacy = world
    cat = Planner.catalogue([modern.describe(), legacy.describe()])
    assert "hostfs://demo" in cat and "hostfs://inbox" in cat
    assert '"id": "doom"' in cat
    assert "someone" not in cat and "C:/" not in cat


def test_list_then_read_the_newest_then_copy_then_launch(world):
    relay, modern, legacy = world
    text = json.dumps({"understood": "", "refused": None, "steps": [
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "hostfs://demo"}},
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": {"$from": {"step": 1, "field": "newest"}}}},
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": "hostfs://inbox/copia.png",
                    "content": {"$from": {"step": 2, "field": "text"}}}},
        {"host": "win98-retrobox", "capability": "apps.launch",
         "params": {"app": "doom"}},
    ]})
    descs = [modern.describe(), legacy.describe()]
    plan = Planner(ScriptedProvider([text])).plan("intent", descs)
    run = Executor(relay, "test").run(plan)
    assert run.completed, run.stop_reason
    assert legacy.fs.read("C:/NEMO/INBOX/copia.png") == "BBB"
    assert legacy.launched == ["DOOM.EXE"]


# -- composing a name from typed references ---------------------------------

def _plan(steps, descs):
    text = json.dumps({"understood": "", "refused": None, "steps": steps})
    return Planner(ScriptedProvider([text])).plan("intent", descs)


def test_a_listing_names_its_newest_file_by_name_too(world):
    _, modern, _ = world
    r = act(modern, "filesystem.read", path="hostfs://demo")
    assert r.result["newest_name"] == "b.png"


def test_copy_the_newest_under_its_own_name_with_join(world):
    relay, modern, legacy = world
    plan = _plan([
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "hostfs://demo"}},
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": {"$from": {"step": 1, "field": "newest"}}}},
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": {"$join": ["hostfs://inbox/",
                                       {"$from": {"step": 1, "field": "newest_name"}}]},
                    "content": {"$from": {"step": 2, "field": "text"}}}},
    ], [modern.describe(), legacy.describe()])
    run = Executor(relay, "test").run(plan)
    assert run.completed, run.stop_reason
    assert legacy.fs.read("C:/NEMO/INBOX/b.png") == "BBB"


@pytest.mark.parametrize("join, reason", [
    (["hostfs://inbox/", {"$from": {"step": 1, "field": "filename"}}], "UNKNOWN_RESULT_FIELD"),
    (["hostfs://inbox/", {"$from": {"step": 2, "field": "path"}}], "BAD_REFERENCE"),
    (["hostfs://inbox/", {"name": "x"}], "BAD_REFERENCE"),
    ("hostfs://inbox/x", "BAD_REFERENCE"),
    ([], "BAD_REFERENCE"),
])
def test_a_join_is_validated_like_any_reference(world, join, reason):
    _, modern, legacy = world
    from agents.planner import PlanRejected
    with pytest.raises(PlanRejected) as exc:
        _plan([
            {"host": "win11-victus", "capability": "filesystem.read",
             "params": {"path": "hostfs://demo"}},
            {"host": "win98-retrobox", "capability": "filesystem.write",
             "params": {"path": {"$join": join}, "content": "x"}},
        ], [modern.describe(), legacy.describe()])
    assert exc.value.reason == reason
