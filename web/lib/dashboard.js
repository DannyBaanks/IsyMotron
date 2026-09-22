export function buildDashboardSnapshot(state = {}) {
  const host = state.hosts?.[0];
  const identity = host?.identity ?? {};
  const awareness = state.awareness?.snapshot ?? {};
  const health = host?.health ?? {};

  return {
    connected: Boolean(host),
    host: {
      label: identity.display_name ?? "Awaiting host",
      id: identity.host_id ?? "—",
      status: awareness.power_state ?? health.power_state ?? "UNKNOWN",
      network: awareness.network_state ?? health.network_state ?? "UNKNOWN",
      epoch: health.power_epoch ?? awareness.power_epoch ?? 0,
      capabilities: host?.granted?.length ?? 0,
    },
    capabilities: host?.capabilities ?? [],
    receipts: (state.receipts ?? []).map((receipt) => ({
      id: receipt.receipt_id ?? "pending",
      decision: receipt.decision?.decision ?? "UNKNOWN",
      capability: receipt.capability ?? "capability",
      seal: receipt.seal_ok === true ? "SEALED" : "PENDING",
    })).reverse(),
  };
}
