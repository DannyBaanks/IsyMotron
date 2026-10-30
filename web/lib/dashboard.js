function flowCaption(receipt) {
  const verified = receipt.seal_ok === true;
  const decision = receipt.decision?.decision;
  const outcome = decision === "ALLOW" ? "La última solicitud fue permitida" : decision === "DENY" ? "La última solicitud fue rechazada" : "La última solicitud no tiene una decisión reconocida";
  return {
    title: verified ? "Recibo verificado" : "Sello pendiente",
    detail: `${outcome}; ${verified ? "su sello está verificado" : "su sello no está verificado"}.`,
    verified,
  };
}

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
      action: receipt.action ?? null,
      owner: receipt.owner ?? receipt.execution_owner ?? null,
      observedAt: receipt.observed_at ?? receipt.created_at ?? null,
      source: receipt.source ?? null,
      freshness: receipt.freshness ?? null,
      seal: receipt.seal_ok === true ? "SEALED" : "PENDING",
      flowCaption: flowCaption(receipt),
    })).reverse(),
  };
}
