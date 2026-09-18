"""Host awareness and attribution.

The eight cases the compose froze, plus the mechanism tests. Everything here
uses `TestPowerProvider`, so proving that a suspend is attributed correctly
never requires physically closing a laptop.

The case that motivated all of it is B: on 2026-09-17 a run that looked exactly
like provider throttling was a closed lid, and nothing in the process could
tell the difference.
"""
from __future__ import annotations

import pytest

from isymotron.attribution import Attribution, attribute
from isymotron.awareness import (
    HostAwarenessEngine,
    HostEventType,
    NetworkState,
    NullPowerProvider,
    PowerState,
    TestPowerProvider,
)
from isymotron.verdicts import Evidence
from agents.provider import ProviderError, ScriptedProvider


@pytest.fixture
def clock():
    return TestPowerProvider()


@pytest.fixture
def engine(clock):
    return HostAwarenessEngine("test-host", clock)


# -- the mechanism ----------------------------------------------------------

def test_a_quiet_host_never_changes_epoch(engine, clock):
    before = engine.snapshot()
    clock.advance(600.0)
    after = engine.snapshot()
    assert before.same_continuity_as(after)
    assert after.power_epoch == 0
    assert after.power_state is PowerState.ACTIVE


def test_a_suspend_advances_power_epoch_and_records_the_gap(engine, clock):
    engine.snapshot()
    clock.suspend(671.4)
    after = engine.snapshot()
    assert after.power_epoch == 1
    resumed = engine.recent_events(types=[HostEventType.HOST_RESUMED])
    assert len(resumed) == 1
    assert resumed[0].detail["suspend_wall_gap_s"] == pytest.approx(671.4, abs=0.01)
    assert resumed[0].detail["previous_power_epoch"] == 0
    assert resumed[0].evidence is Evidence.DEMONSTRATED


def test_wall_time_advances_through_a_suspend_but_awake_time_does_not(engine, clock):
    """The heart of it. Wall and monotonic both move through sleep, which is
    why comparing them cannot detect a suspend on Windows."""
    before = engine.snapshot()
    clock.suspend(793.0)
    clock.advance(2.0)
    after = engine.snapshot()
    assert before.elapsed_wall(after) == pytest.approx(795.0, abs=0.01)
    assert before.elapsed_awake(after) == pytest.approx(2.0, abs=0.01)


def test_sub_threshold_noise_is_not_a_suspend(engine, clock):
    engine.snapshot()
    clock._bias += 0.0022     # the drift measured on the real machine
    after = engine.snapshot()
    assert after.power_epoch == 0


def test_no_mechanism_means_unknown_not_active():
    """Invariant 10: absence of evidence must never become ACTIVE."""
    engine = HostAwarenessEngine("blind-host", NullPowerProvider())
    snap = engine.snapshot()
    assert snap.power_state is PowerState.UNKNOWN
    assert engine.health()["suspend_observable"] is False
    assert snap.unbiased_time is None


def test_elapsed_awake_is_none_without_an_unbiased_clock():
    """None, not zero. A missing measurement is not a measurement of nothing."""
    engine = HostAwarenessEngine("blind-host", NullPowerProvider())
    a = engine.snapshot()
    b = engine.snapshot()
    assert a.elapsed_awake(b) is None


def test_network_change_advances_network_epoch(engine, clock):
    engine.snapshot()
    clock.network_down()
    after = engine.snapshot()
    assert after.network_epoch == 1
    assert after.network_state is NetworkState.DOWN
    assert engine.recent_events(types=[HostEventType.NETWORK_DOWN])


def test_reboot_changes_boot_id(engine, clock):
    before = engine.snapshot()
    clock.reboot()
    after = engine.snapshot()
    assert before.boot_id != after.boot_id
    assert engine.recent_events(types=[HostEventType.HOST_BOOT])


def test_the_engine_has_the_four_operations(engine):
    for op in ("describe", "snapshot", "recent_events", "health"):
        assert callable(getattr(engine, op))


# -- the eight required cases ----------------------------------------------

def test_case_A_provider_error_with_the_host_awake(engine, clock):
    before = engine.snapshot()
    clock.advance(1.2)
    after = engine.snapshot()
    o = attribute(before, after, http_status=429, deadline_s=90)
    assert o.attribution is Attribution.PROVIDER_ERROR
    assert o.host_interruption is False
    assert o.provider_fault is True
    assert o.countable is True


def test_case_B_suspend_mid_request_is_not_a_provider_error(engine, clock):
    """The 2026-09-17 incident, reproduced deterministically."""
    before = engine.snapshot()
    clock.advance(1.0)
    clock.suspend(791.0)
    clock.advance(1.0)
    after = engine.snapshot()
    o = attribute(before, after, error=OSError("connection reset"),
                  transport=True, deadline_s=90)
    assert o.attribution is Attribution.HOST_SUSPENDED
    assert o.provider_fault is False
    assert o.host_interruption is True
    assert "says nothing about the provider" in o.reason
    assert o.wall_elapsed_s == pytest.approx(793.0, abs=0.01)
    assert o.awake_elapsed_s == pytest.approx(2.0, abs=0.01)


def test_case_C_network_loss_without_suspend(engine, clock):
    before = engine.snapshot()
    clock.advance(1.0)
    clock.network_down()
    after = engine.snapshot()
    o = attribute(before, after, error=OSError("unreachable"), transport=True)
    assert o.attribution is Attribution.HOST_NETWORK_LOSS
    assert o.attribution is not Attribution.HOST_SUSPENDED
    assert o.provider_fault is False


def test_case_D_deadline_exceeded_with_the_host_awake(engine, clock):
    before = engine.snapshot()
    clock.advance(120.0)
    after = engine.snapshot()
    o = attribute(before, after, error=TimeoutError(), transport=True, deadline_s=90)
    assert o.attribution is Attribution.DEADLINE_EXCEEDED
    assert o.host_interruption is False
    assert "host awake throughout" in o.reason


def test_case_E_insufficient_evidence_is_unknown():
    """A transport failure on a host that cannot see its own network is
    genuinely ambiguous, and says so rather than blaming the provider."""
    blind = HostAwarenessEngine("blind-host", NullPowerProvider())
    before = blind.snapshot()
    after = blind.snapshot()
    o = attribute(before, after, error=OSError("reset"), transport=True)
    assert o.attribution is Attribution.UNKNOWN
    assert o.provider_fault is False
    assert o.countable is False


def test_case_F_a_suspended_measurement_is_excluded_from_provider_stats(engine, clock):
    """The suspend must land *during* a call, not between two of them --
    that is the scenario, and modelling it wrong is how the first version of
    this test passed for the wrong reason."""
    p = ScriptedProvider(["ok-1"], awareness=engine)
    p.complete([{"role": "user", "content": "hi"}])       # clean call

    p2 = ScriptedProvider(["ok-2"], awareness=engine,
                          during=lambda: clock.suspend(400.0))
    p2.complete([{"role": "user", "content": "hi"}])      # suspended call
    p.countable_calls += p2.countable_calls
    p.provider_faults += p2.provider_faults
    p.excluded_host_faults += p2.excluded_host_faults

    r = p.reliability()
    assert r["countable_calls"] == 1, "the suspended call must not be counted"
    assert r["excluded_host_faults"] == 1, "and must not be silently dropped"
    assert r["provider_faults"] == 0
    assert r["fault_rate"] == 0.0


def test_case_G_process_restart_is_detected(clock):
    first = HostAwarenessEngine("test-host", clock)
    before = first.snapshot()
    second = HostAwarenessEngine("test-host", clock)   # a new process
    after = second.snapshot()
    o = attribute(before, after, error=OSError("gone"), transport=True)
    assert o.attribution is Attribution.PROCESS_INTERRUPTED
    assert o.provider_fault is False


def test_case_H_a_model_cannot_manufacture_a_host_event(engine):
    """Invariant 7: a model may interpret these events and never create one."""
    with pytest.raises(NotImplementedError):
        engine.ingest_external({"event": "HOST_SUSPENDED", "host": "test-host"})
    assert not engine.recent_events(types=[HostEventType.HOST_RESUMED])
    assert engine.snapshot().power_epoch == 0


# -- integration with the provider -----------------------------------------

def test_ok_calls_are_countable(engine):
    p = ScriptedProvider(["a", "b", "c"], awareness=engine)
    for _ in range(3):
        p.complete([{"role": "user", "content": "hi"}])
    assert p.reliability()["countable_calls"] == 3
    assert p.reliability()["fault_rate"] == 0.0


def test_reliability_says_so_when_it_cannot_tell(engine):
    blind = ScriptedProvider(["a"])
    blind.complete([{"role": "user", "content": "hi"}])
    assert blind.reliability()["host_awareness"] is False
    assert "cannot tell" in blind.reliability()["note"]

    aware = ScriptedProvider(["a"], awareness=engine)
    aware.complete([{"role": "user", "content": "hi"}])
    assert aware.reliability()["host_awareness"] is True


def test_a_completion_carries_its_attribution(engine):
    p = ScriptedProvider(["hola"], awareness=engine)
    c = p.complete([{"role": "user", "content": "hi"}])
    assert c.outcome is not None
    assert c.outcome.attribution is Attribution.OK
    assert c.to_dict()["outcome"]["attribution"] == "OK"


def test_awareness_grants_nothing():
    """Invariants 3-5: facts, not authority. The engine has no verb that
    could allow, execute or change a grant."""
    engine = HostAwarenessEngine("test-host", TestPowerProvider())
    forbidden = ("execute", "allow", "grant", "request_lease", "decide",
                 "authorize", "run")
    for name in forbidden:
        assert not hasattr(engine, name), f"awareness must not expose {name}()"
