from __future__ import annotations

import sys
import time

import pytest

from hosts.linux.power import LinuxPowerProvider
from isymotron.awareness import NetworkState


LINUX_NATIVE = pytest.mark.skipif(
    sys.platform != "linux",
    reason="CLOCK_BOOTTIME and CLOCK_MONOTONIC are Linux-native clocks",
)


@LINUX_NATIVE
def test_linux_provider_reads_native_clocks():
    provider = LinuxPowerProvider()
    sample = provider.sample()

    assert sample.source == "linux-seam"
    assert sample.unbiased_time is not None
    assert sample.suspend_bias_s is not None
    assert sample.suspend_bias_s >= 0.0
    assert sample.detail["status"] == "DEMONSTRATED"


def test_linux_provider_describes_native_mechanisms():
    description = LinuxPowerProvider().describe()

    assert description["implemented"] is True
    assert description["evidence"] == "DEMONSTRATED"
    assert description["pre_suspend_notification"] is False


def test_linux_provider_network_probe_is_local_and_bounded(monkeypatch, tmp_path):
    net = tmp_path / "net"
    eth = net / "eth0"
    eth.mkdir(parents=True)
    (eth / "operstate").write_text("up\n", encoding="ascii")
    monkeypatch.setattr(LinuxPowerProvider, "_NET_ROOT", str(net))
    assert LinuxPowerProvider()._network() is NetworkState.UP


@LINUX_NATIVE
def test_native_clocks_are_monotonic_for_awake_sample():
    provider = LinuxPowerProvider()
    first = provider.sample()
    time.sleep(0.01)
    second = provider.sample()
    assert second.monotonic_time >= first.monotonic_time
    assert second.suspend_bias_s >= first.suspend_bias_s
