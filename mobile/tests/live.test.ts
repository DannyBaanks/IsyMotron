/**
 * The phone's client against the PC's real Link server (Python, core/isymotron/link), over
 * real HTTP on localhost. A line-driven helper plays the human at the PC typing the code.
 */
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { delegate, ping, requestPairing, task, cancel, type Fetch } from "../src/link/client";
import { loadOrCreateIdentity, memoryKeyStore } from "../src/link/keystore";

const helper = fileURLToPath(new URL("../tools/link_pc_for_tests.py", import.meta.url));
let pc: ChildProcessWithoutNullStreams;
let next: () => Promise<Record<string, unknown>>;
let port = 0;

beforeAll(async () => {
  pc = spawn("python3", [helper]);
  const lines = createInterface({ input: pc.stdout })[Symbol.asyncIterator]();
  next = async () => JSON.parse((await lines.next()).value as string);
  port = Number((await next()).port);
});
afterAll(() => {
  pc.stdin.write("quit\n");
  pc.kill();
});
const pcSays = async (cmd: string) => (pc.stdin.write(`${cmd}\n`), next());
const f: Fetch = (url, init) => fetch(url, init);

describe("phone ↔ PC over the real Link server", () => {
  it("pairs with the 6-digit code, then pings, delegates, follows and cancels a task", async () => {
    const phone = await loadOrCreateIdentity(memoryKeyStore(), "isytron-telefono-test");
    const address = `127.0.0.1:${port}`;

    const proposal = await requestPairing(phone, address, f);
    expect(proposal.code).toMatch(/^\d{6}$/);

    // Not paired yet on the PC: a sealed call is refused.
    await expect(ping(phone, proposal.peer, f)).rejects.toMatchObject({ code: "rejected" });

    // The human at the PC types the code the phone shows.
    const accepted = await pcSays(`accept ${proposal.code}`);
    expect(accepted.accepted).toBe(true);
    expect((accepted.peer as { office_id: string }).office_id).toBe(phone.officeId);

    expect(await ping(phone, proposal.peer, f)).toMatchObject({ ok: true, pong: true, from: proposal.peer.office_id });
    const sent = await delegate(phone, proposal.peer, "Revisar el respaldo", "hola 🐱 desde el teléfono", f);
    const taskId = String(sent.task_id);
    expect(taskId).toMatch(/^task-/);

    const inbox = (await pcSays("inbox")).inbox as Array<Record<string, unknown>>;
    expect(inbox).toEqual([expect.objectContaining({ task_id: taskId, from: phone.officeId, title: "Revisar el respaldo", body: "hola 🐱 desde el teléfono", status: "queued" })]);
    const receipts = (await pcSays("receipts")).receipts as Array<Record<string, unknown>>;
    expect(JSON.stringify(receipts)).toContain("link_received");

    expect(await task(phone, proposal.peer, taskId, f)).toMatchObject({ task: { task_id: taskId, status: "queued" } });
    await cancel(phone, proposal.peer, taskId, f);
    expect(await task(phone, proposal.peer, taskId, f)).toMatchObject({ task: { status: "cancelled" } });
  });

  it("a wrong code on the PC pairs nothing", async () => {
    const phone = await loadOrCreateIdentity(memoryKeyStore(), "isytron-otro");
    const proposal = await requestPairing(phone, `127.0.0.1:${port}`, f);
    const wrong = proposal.code === "000000" ? "111111" : "000000";
    expect((await pcSays(`accept ${wrong}`)).accepted).toBe(false);
    await expect(ping(phone, proposal.peer, f)).rejects.toMatchObject({ code: "rejected" });
  });
});
