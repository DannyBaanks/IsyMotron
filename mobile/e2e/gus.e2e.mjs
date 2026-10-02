import assert from "node:assert/strict";
import { chromium } from "playwright";
import { spawn } from "node:child_process";

const preview = spawn("npx", ["vite", "preview", "--mode", "e2e", "--port", "4175", "--strictPort"], { stdio: "ignore" });
let browser;
try {
  let ready = false;
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch("http://localhost:4175/")).ok) { ready = true; break; } } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  assert.ok(ready, "GUS e2e preview did not start");
  browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  let remoteCalls = 0;
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.route("https://integrate.api.nvidia.com/**", async (route) => {
    remoteCalls++;
    const body = JSON.parse(route.request().postData() ?? "{}");
    assert.equal(body.model, "nvidia/nemotron-3-nano-30b-a3b");
    assert.equal(route.request().headers().authorization, "Bearer e2e-only-key");
    assert.equal(JSON.stringify(body).includes("e2e-only-key"), false);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ choices: [{ message: { content: "NIM simulado" } }] }) });
  });
  await page.goto("http://localhost:4175/");
  await page.getByRole("button", { name: /Abrir GUS/ }).click();
  await page.getByRole("heading", { name: "GUS" }).waitFor();
  await page.getByText(/2\.84 GB de descarga|Descarga de 2\.84 GB/).waitFor();
  await page.getByText(/rendimiento, RAM, batería y temperatura en teléfonos: NOT DEMONSTRATED/).waitFor();

  await page.getByRole("button", { name: "Descargar y verificar" }).first().click();
  await page.getByText("Modelo verificado e instalado.").waitFor();
  await page.getByRole("button", { name: /Guardar copia externa/ }).first().click();
  await page.getByText("Copia del modelo guardada.").waitFor();
  await page.getByRole("button", { name: "Importar copia guardada con iSyCode" }).click();
  await page.getByText(/Importación completada/).waitFor();

  await page.getByLabel("Mensaje para GUS").fill("fallo local e2e");
  await page.getByRole("button", { name: "Enviar" }).click();
  await page.getByText(/runtime local falló de forma simulada/).waitFor();
  assert.equal(remoteCalls, 0, "local failure must never trigger a remote request");

  await page.getByRole("button", { name: "Usar preset NVIDIA NIM" }).click();
  await page.getByLabel("API key del proveedor remoto").fill("e2e-only-key");
  await page.getByRole("button", { name: "Guardar configuración y API key" }).click();
  await page.locator(".gus-remote").getByText("API key guardada en almacenamiento seguro.").waitFor();
  await page.getByLabel("Mensaje para GUS").fill("hola remoto");
  await page.getByRole("button", { name: "Enviar" }).click();
  await page.getByText("NIM simulado").waitFor();
  assert.equal(remoteCalls, 1, "one request should be sent only after remote mode is selected and submitted");
  assert.deepEqual(errors, []);
  console.log("GUS e2e PASS: model controls, Nemotron limits, local failure isolation, explicit NVIDIA NIM request");
} finally {
  await browser?.close();
  preview.kill();
}
