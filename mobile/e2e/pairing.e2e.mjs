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
import { fileURLToPath } from "node:url";
const SP = process.env.E2E_OUT ?? "e2e-out";
mkdirSync(SP, { recursive: true });
const pc = spawn("python3", [fileURLToPath(new URL("../tools/link_pc_for_tests.py", import.meta.url))]);
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
const before = await p.textContent("main p[aria-live]");
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
const permission = await say("request-permission");
const permissionId = permission.request.request_id;
const secondPermission = await say("request-permission");
const secondPermissionId = secondPermission.request.request_id;
await p.click(".tabbar >> text=Permisos");
await p.waitForSelector("text=Read the requested photo");
await p.locator(".permission-card").nth(0).getByRole("button", { name: "Sí, aprobar" }).click();
await p.waitForSelector("text=Permiso aprobado");
const decidedPermission = await say(`permission-status ${permissionId}`);
assert.equal(decidedPermission.request.status, "approved");
assert.deepEqual(decidedPermission.request.lease.scope, { roots: ["/srv/photos"] });
await p.locator(".permission-card").nth(0).getByRole("button", { name: "No, rechazar" }).click();
await p.waitForSelector("text=Permiso rechazado");
const deniedPermission = await say(`permission-status ${secondPermissionId}`);
assert.equal(deniedPermission.request.status, "denied");
assert.equal("lease" in deniedPermission.request, false);
const permissionReceipts = (await say("receipts")).receipts;
assert.ok(permissionReceipts.some((r) => r.kind === "link_permission_decided" && r.request_id === permissionId && r.decision === "approved"));
assert.ok(permissionReceipts.some((r) => r.kind === "link_permission_decided" && r.request_id === secondPermissionId && r.decision === "denied"));
await p.click(".tabbar >> text=Recibos");
await p.waitForSelector("text=Permiso aprobado");
await p.click(".tabbar >> text=Permisos");
await p.screenshot({ path: SP + "/e2e-peer.png", fullPage: true });
await p.click(".tabbar >> text=Inicio");
await p.locator(".pc .row-btn").click();
await p.click("text=Volver");
assert.equal(await p.isVisible(".row-btn"), true);
await p.reload();
await p.waitForSelector(".row-btn");
// Malbolgato v2 is on Inicio, drawn from the atlas, and a long press opens his controls.
assert.match(await p.evaluate(() => getComputedStyle(document.querySelector(".sprite")).backgroundImage), /malbolgato\/atlas\.webp/);
const pet = await p.locator(".pet").boundingBox();
await p.mouse.move(pet.x + pet.width / 2, pet.y + pet.height / 2);
await p.mouse.down(); await p.waitForTimeout(650); await p.mouse.up();
await p.waitForSelector('[aria-label="Controles de Malbolgato"]');
await p.screenshot({ path: SP + "/e2e-home-controls.png" });
await p.click("text=Cerrar");
for (const tab of ["Tareas", "Permisos", "Recibos", "Teléfono", "Inicio"]) await p.click(`.tabbar >> text=${tab}`);
await p.screenshot({ path: SP + "/e2e-home.png" });
assert.deepEqual(errors, []);
console.log("e2e OK: paired, task delivered/cancelled, permission approved, still paired after reload");
pc.stdin.write("quit\n");
await b.close();
preview.kill();
