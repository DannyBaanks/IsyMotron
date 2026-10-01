/**
 * End to end, as a person would use it: the built app in Chromium, tapping the real buttons,
 * against the PC's real Link server (Python). Pair (refused before the PC accepts, then
 * accepted), send a task, see it land in the PC's inbox, follow it, cancel it, reload and
 * still be paired. Run after `npm run build`:  node e2e/pairing.e2e.mjs
 */
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { mkdirSync } from "node:fs";
const SP = process.env.E2E_OUT ?? "e2e-out";
mkdirSync(SP, { recursive: true });
const pc = spawn("python3", [new URL("../tools/link_pc_for_tests.py", import.meta.url).pathname]);
const lines = createInterface({ input: pc.stdout })[Symbol.asyncIterator]();
const next = async () => JSON.parse((await lines.next()).value);
const say = async (c) => (pc.stdin.write(c + "\n"), next());
const { port } = await next();
const preview = spawn("npx", ["vite", "preview", "--port", "4174", "--strictPort"], { stdio: "ignore" });
for (let i = 0; i < 50; i++) { try { if ((await fetch("http://localhost:4174/")).ok) break; } catch {} await new Promise((r) => setTimeout(r, 200)); }
const b = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const p = await b.newPage({ viewport: { width: 390, height: 844 } });
const errors = []; p.on("pageerror", (e) => errors.push(String(e)));
const cors = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type", "access-control-allow-methods": "GET,POST,OPTIONS" };
// The native app has no CORS (CapacitorHttp); in a browser we add the headers in transit.
await p.route("http://127.0.0.1:" + port + "/**", async (route) => {
  if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
  const res = await route.fetch();
  await route.fulfill({ response: res, headers: { ...res.headers(), ...cors } });
});
await p.goto("http://localhost:4174/");
await p.click("text=Enlazar con mi PC");
await p.fill('[aria-label="Dirección de tu PC"]', "127.0.0.1:" + port);
await p.click("text=Pedir enlace");
await p.waitForSelector(".code");
const code = (await p.textContent(".code")).replace(/\s/g, "");
await p.screenshot({ path: SP + "/e2e-code.png" });
await p.click("text=Ya lo escribí en mi PC");
await p.waitForTimeout(700);
const before = await p.textContent("section [aria-live]");
assert.match(before, /no aceptó/);
console.log("before accept:", before);
assert.equal((await say("accept " + code)).accepted, true);
await p.click("text=Ya lo escribí en mi PC");
await p.waitForSelector("text=Enlazado con");
await p.fill('[aria-label="Título de la tarea"]', "Revisar el respaldo");
await p.fill('[aria-label="Detalles de la tarea"]', "hola 🐱 desde el teléfono");
await p.click("text=Mandar a mi PC");
await p.waitForSelector("text=Tarea en la bandeja");
assert.deepEqual((await say("inbox")).inbox.map((t) => [t.title, t.body, t.status]), [["Revisar el respaldo", "hola 🐱 desde el teléfono", "queued"]]);
await p.click("text=Ver estado");
await p.waitForSelector("text=· queued");
await p.click(".task >> text=Cancelar");
await p.waitForSelector("text=· cancelled");
assert.deepEqual((await say("inbox")).inbox.map((t) => t.status), ["cancelled"]);
await p.screenshot({ path: SP + "/e2e-peer.png", fullPage: true });
await p.click("text=Volver");
assert.equal(await p.isVisible(".row-btn"), true);
await p.reload();
await p.waitForSelector(".row-btn");
assert.deepEqual(errors, []);
console.log("e2e OK: paired, task delivered, followed, cancelled, still paired after reload");
pc.stdin.write("quit\n");
await b.close();
preview.kill();
