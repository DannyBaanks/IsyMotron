import test from "node:test";
import assert from "node:assert/strict";
import { buildDashboardSnapshot } from "./dashboard.js";

test("buildDashboardSnapshot maps a host and awareness into the status rail", () => {
  const snapshot = buildDashboardSnapshot({
    hosts: [{
      identity: { host_id: "host-03", display_name: "Michael" },
      granted: ["filesystem.read"],
      health: { power_state: "ACTIVE", network_state: "UP", power_epoch: 2 },
      capabilities: [{ id: "filesystem.read", state: "GRANTED" }],
    }],
    awareness: { snapshot: { power_state: "ACTIVE", network_state: "UP" } },
    receipts: [{ decision: { decision: "ALLOW" }, receipt_id: "rcpt_01" }],
  });

  assert.equal(snapshot.host.label, "Michael");
  assert.equal(snapshot.host.status, "ACTIVE");
  assert.equal(snapshot.host.network, "UP");
  assert.equal(snapshot.host.epoch, 2);
  assert.equal(snapshot.receipts[0].decision, "ALLOW");
});

test("buildDashboardSnapshot keeps an empty backend visibly disconnected", () => {
  const snapshot = buildDashboardSnapshot({});

  assert.equal(snapshot.host.label, "Awaiting host");
  assert.equal(snapshot.host.status, "UNKNOWN");
  assert.equal(snapshot.connected, false);
  assert.deepEqual(snapshot.receipts, []);
});
