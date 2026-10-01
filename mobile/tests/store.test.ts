import { addReceipt, forgetPeer, loadPeers, loadReceipts, MAX_RECEIPTS, memoryKv, spacedCode, trustPeer } from "../src/store";

const peer = { office_id: "9fab99d9e5571b1a", name: "isytron-pc", sign_pub: "s", box_pub: "b", addresses: ["192.168.1.20:47931"] };

describe("what the phone remembers", () => {
  it("pins a PC once (first paired_at wins), merges addresses, forgets on request", () => {
    const kv = memoryKv();
    const first = trustPeer(kv, peer, new Date("2026-10-01T00:00:00Z"));
    const again = trustPeer(kv, { ...peer, addresses: ["10.0.0.5:47931"] }, new Date("2026-10-02T00:00:00Z"));
    expect(again.paired_at).toBe(first.paired_at);
    expect(again.addresses.sort()).toEqual(["10.0.0.5:47931", "192.168.1.20:47931"]);
    expect(JSON.stringify(loadPeers(kv))).not.toMatch(/"d"|private/i);
    forgetPeer(kv, peer.office_id);
    expect(loadPeers(kv)).toEqual({});
  });

  it("keeps the last receipts only and survives garbage", () => {
    const kv = memoryKv();
    for (let i = 0; i < MAX_RECEIPTS + 5; i++) addReceipt(kv, { kind: "link_delegated", office_id: peer.office_id, name: peer.name, task_id: `t${i}` });
    expect(loadReceipts(kv)).toHaveLength(MAX_RECEIPTS);
    expect(loadReceipts(kv).at(-1)!.task_id).toBe(`t${MAX_RECEIPTS + 4}`);
    kv.setItem("isymotron.peers.v1", "{nope");
    expect(loadPeers(kv)).toEqual({});
  });

  it("shows the code in two groups", () => {
    expect(spacedCode("012345")).toBe("012 345");
  });
});

import { describeReceipt } from "../src/home";

describe("receipts read like a sentence", () => {
  it("names what happened and with which PC", () => {
    const base = { at: "2026-10-01T10:24:00Z", office_id: "x", name: "isytron-pc" };
    expect(describeReceipt({ ...base, kind: "link_delegated", title: "Revisar el respaldo" })).toBe("Tarea enviada · Revisar el respaldo → isytron-pc");
    expect(describeReceipt({ ...base, kind: "link_paired" })).toBe("PC enlazada · isytron-pc");
  });
});
