"""M3 gate — planner and executor, offline.

Every test here uses `ScriptedProvider`, so the suite stays deterministic, free
and runnable with no key. What is under test is the *validation*: what happens
to a model reply, not what a model says. Tests that need a live model live in
`tests/test_live_model.py` and skip without a key.
"""
from __future__ import annotations

import json

import pytest

from agents.executor import Executor, looks_like_a_placeholder
from agents.planner import Plan, PlanRejected, Planner
from agents.provider import Completion, ProviderError, Provider, ScriptedProvider
from isymotron.verdicts import Decision
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost


@pytest.fixture
def world():
    modern = ModernHost(
        fs={"C:/Photos/a.png": "AAA", "C:/Photos/b.png": "BBB"},
        granted=["filesystem.read", "system.info"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}, "system.info": {}},
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
    return relay, [modern.describe(), legacy.describe()], modern, legacy


def reply(**obj) -> str:
    obj.setdefault("understood", "")
    obj.setdefault("steps", [])
    obj.setdefault("refused", None)
    return json.dumps(obj)


def plan_from(text, descs) -> Plan:
    return Planner(ScriptedProvider([text])).plan("intent", descs)


# -- the catalogue is the only thing the model may know ---------------------

def test_catalogue_omits_ungranted_capabilities(world):
    _, descs, modern, _ = world
    cat = Planner.catalogue(descs)
    assert "filesystem.read" in cat
    assert "process.inspect" not in cat, "an ungranted capability must not appear"
    assert "apps.launch" in cat


def test_catalogue_declares_result_fields(world):
    """Regression for FINDINGS.md #5: without `returns`, a cross-step
    reference is a guess, and two engines disagreed on the name."""
    _, descs, _, _ = world
    cat = Planner.catalogue(descs)
    assert "returns:" in cat
    assert "text" in cat


def test_both_engines_agree_on_result_field_names(world):
    _, descs, modern, legacy = world
    m = next(c for c in modern.describe().capabilities if c.id == "filesystem.read")
    lg = LegacyHost(fs={}, granted=[], grant_scopes={})
    l = next(c for c in lg.describe().capabilities if c.id == "filesystem.read")
    assert tuple(m.returns) == tuple(l.returns)


# -- validation rejects what the enforcer would never see -------------------

def test_hallucinated_capability_is_rejected(world):
    _, descs, _, _ = world
    text = reply(steps=[{"host": "win11-victus", "capability": "system.disable_firewall",
                         "params": {}}])
    with pytest.raises(PlanRejected) as e:
        plan_from(text, descs)
    assert e.value.reason == "UNKNOWN_CAPABILITY"


def test_ungranted_but_real_capability_is_rejected_the_same_way(world):
    """process.inspect exists on the engine but was never granted. The model
    never saw it, so asking for it is indistinguishable from inventing it."""
    _, descs, _, _ = world
    text = reply(steps=[{"host": "win11-victus", "capability": "process.inspect",
                         "params": {}}])
    with pytest.raises(PlanRejected) as e:
        plan_from(text, descs)
    assert e.value.reason == "UNKNOWN_CAPABILITY"


def test_unknown_host_is_rejected(world):
    _, descs, _, _ = world
    text = reply(steps=[{"host": "win95-basement", "capability": "system.info",
                         "params": {}}])
    with pytest.raises(PlanRejected) as e:
        plan_from(text, descs)
    assert e.value.reason == "UNKNOWN_HOST"


def test_undeclared_param_is_rejected(world):
    _, descs, _, _ = world
    text = reply(steps=[{"host": "win11-victus", "capability": "filesystem.read",
                         "params": {"path": "C:/Photos/a.png", "sudo": True}}])
    with pytest.raises(PlanRejected) as e:
        plan_from(text, descs)
    assert e.value.reason == "UNDECLARED_PARAMS"


def test_forward_reference_is_rejected(world):
    _, descs, _, _ = world
    text = reply(steps=[
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": "C:/NEMO/INBOX/x", "content": {"$from": {"step": 2, "field": "text"}}}},
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Photos/a.png"}},
    ])
    with pytest.raises(PlanRejected) as e:
        plan_from(text, descs)
    assert e.value.reason == "BAD_REFERENCE"


def test_reference_to_an_undeclared_result_field_is_rejected(world):
    _, descs, _, _ = world
    text = reply(steps=[
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Photos/a.png"}},
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": "C:/NEMO/INBOX/x",
                    "content": {"$from": {"step": 1, "field": "content"}}}},
    ])
    with pytest.raises(PlanRejected) as e:
        plan_from(text, descs)
    assert e.value.reason == "UNKNOWN_RESULT_FIELD"
    assert "text" in e.value.detail


def test_truncation_is_not_reported_as_bad_json(world):
    """Regression for FINDINGS.md #3. These have opposite fixes: TRUNCATED
    means raise the budget, NOT_JSON means fix the prompt. On a reasoning
    model a truncated reply arrives as raw chain-of-thought, which looks
    exactly like a model that cannot follow instructions."""
    _, descs, _, _ = world
    with pytest.raises(PlanRejected) as e:
        plan_from("<TRUNCATED>We need to think about which host has the", descs)
    assert e.value.reason == "TRUNCATED"

    with pytest.raises(PlanRejected) as e:
        plan_from("Sure! I would be happy to help with that.", descs)
    assert e.value.reason == "NOT_JSON"


def test_json_inside_a_fence_is_accepted(world):
    _, descs, _, _ = world
    inner = reply(understood="ok", steps=[{"host": "win11-victus",
                                           "capability": "system.info", "params": {}}])
    p = plan_from(f"Here is the plan:\n```json\n{inner}\n```\nHope that helps.", descs)
    assert len(p.steps) == 1


# -- a refusal is a first-class outcome -------------------------------------

def test_empty_plan_with_a_reason_is_a_refusal_not_a_failure(world):
    _, descs, _, _ = world
    p = plan_from(reply(steps=[], refused="no capability lists files by date"), descs)
    assert p.verdict() == "REFUSED_WITH_REASON"
    assert p.is_refusal()


def test_empty_plan_without_a_reason_is_its_own_class(world):
    _, descs, _, _ = world
    p = plan_from(reply(steps=[]), descs)
    assert p.verdict() == "EMPTY_NO_REASON"


def test_plan_with_steps_is_planned(world):
    _, descs, _, _ = world
    p = plan_from(reply(steps=[{"host": "win11-victus", "capability": "system.info",
                                "params": {}}]), descs)
    assert p.verdict() == "PLANNED"


# -- the executor -----------------------------------------------------------

def test_executor_resolves_a_reference_across_hosts(world):
    relay, descs, _, legacy = world
    p = plan_from(reply(steps=[
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Photos/a.png"}},
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": "C:/NEMO/INBOX/a.png",
                    "content": {"$from": {"step": 1, "field": "text"}}}},
    ]), descs)
    ex = Executor(relay, "test:planner").run(p)
    assert ex.completed
    assert legacy.fs.read("C:/NEMO/INBOX/a.png") == "AAA"


def test_executor_stops_at_the_first_deny(world):
    relay, descs, _, legacy = world
    p = plan_from(reply(steps=[
        {"host": "win98-retrobox", "capability": "apps.launch", "params": {"app": "DOOM"}},
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": "C:/NEMO/INBOX/after.txt", "content": "x"}},
    ]), descs)
    ex = Executor(relay, "test:planner").run(p)
    assert not ex.completed
    assert ex.stopped_at == 1
    assert "OUT_OF_SCOPE" in ex.stop_reason
    assert len(ex.steps) == 1, "nothing after a DENY may run"
    assert "c:/nemo/inbox/after.txt" not in legacy.fs.files


def test_a_plan_carries_no_authority(world):
    """The whole point: a perfectly-formed plan is still judged per step."""
    relay, descs, _, _ = world
    p = plan_from(reply(steps=[
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Secrets/keys.txt"}},
    ]), descs)
    assert p.verdict() == "PLANNED"          # the plan validated fine
    ex = Executor(relay, "test:planner").run(p)
    assert not ex.completed                   # the host still said no
    assert ex.steps[0].receipt.decision.decision is Decision.DENY


def test_prose_placeholder_is_refused_before_it_reaches_a_host(world):
    """Regression for FINDINGS.md #3. Before `$from` existed, the model wrote
    "<content from previous step>" into a parameter. Executing that writes the
    placeholder text to a real file."""
    relay, descs, _, legacy = world
    p = plan_from(reply(steps=[
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": "C:/NEMO/INBOX/x.txt",
                    "content": "<content from previous step>"}},
    ]), descs)
    ex = Executor(relay, "test:planner").run(p)
    assert not ex.completed
    assert "placeholder" in ex.stop_reason
    assert "c:/nemo/inbox/x.txt" not in legacy.fs.files


@pytest.mark.parametrize("value,caught", [
    ("<content from previous step>", True),
    ("the result of step 1", True),
    ("TODO: fill in", True),
    ("contenido del paso anterior", True),
    ("Hola, esto es un fichero normal", False),
    ("step-by-step-guide.txt", False),
])
def test_placeholder_detector(value, caught):
    assert (looks_like_a_placeholder(value) is not None) is caught


def test_executor_reports_which_fields_existed(world):
    relay, descs, _, _ = world
    p = Planner.parse(reply(steps=[
        {"host": "win11-victus", "capability": "system.info", "params": {}},
        {"host": "win98-retrobox", "capability": "filesystem.write",
         "params": {"path": "C:/NEMO/INBOX/x", "content": {"$from": {"step": 1, "field": "os"}}}},
    ]), descs)
    ex = Executor(relay, "test:planner").run(p)
    assert ex.completed


# -- the provider seam ------------------------------------------------------

def test_provider_presets_differ_only_in_door():
    nv = Provider(name="nvidia", api_key="x")
    nb = Provider(name="nebius", api_key="x")
    assert nv.base_url != nb.base_url
    assert nv.model == nb.model, "the same model id string serves on both"


def test_unknown_provider_is_refused():
    with pytest.raises(ProviderError):
        Provider(name="azure-quantum-gpt", api_key="x")


def test_missing_key_is_refused_before_any_request():
    p = Provider(name="nebius", api_key="")
    assert not p.configured()
    with pytest.raises(ProviderError) as e:
        p.complete([{"role": "user", "content": "hi"}])
    assert "NEBIUS_API_KEY" in str(e.value)


def test_truncated_flag():
    assert Completion("x", "m", "p", 0.0, finish_reason="length").truncated
    assert not Completion("x", "m", "p", 0.0, finish_reason="stop").truncated
