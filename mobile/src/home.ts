/**
 * The app's screens, in the "Verde terminal" look with Malbolgato on Inicio. Version 1 pairs
 * the phone with an IsyMotron PC over Link, pings it, hands it tasks and follows them. The PC
 * decides everything; the phone asks, shows sealed answers and keeps its own receipts.
 * Malbolgato only reflects what happened: he has no authority (docs/AVATAR_CONTRACT.md).
 */
import { cancel, decidePermission, delegate, LinkClientError, listPermissions, parseAddress, ping, requestPairing, task, type Fetch, type PairingProposal, type PermissionRequest } from "./link/client";
import type { Peer } from "./link/envelope";
import { prettyFingerprint, type LinkIdentity } from "./link/identity";
import { createPet, ROW, type PetState } from "./pet";
import { addReceipt, forgetPeer, loadPeers, loadReceipts, spacedCode, trustPeer, type KeyValue, type PhoneReceipt } from "./store";
import { canPair, type CryptoSupport } from "./support";
import { createGusChat, type GusAppDeps, type GusChatController } from "./gus/chat";
import { GUS_MODELS } from "./gus/catalog.generated";
import { NVIDIA_NIM_PRESET } from "./gus/remote";
import { composeDelegateFromMessages } from "./gus/compose";

export function supportLines(s: CryptoSupport): string[] {
  const mark = (ok: boolean) => (ok ? "✓" : "✗");
  return [`${mark(s.ed25519)} Firmas Ed25519`, `${mark(s.x25519)} Llaves X25519`, `${mark(s.hkdf)} HKDF-SHA256`, `${mark(s.aesGcm)} AES-GCM`];
}

export function supportVerdict(s: CryptoSupport): string {
  return canPair(s)
    ? "Este teléfono tiene la criptografía que necesita el Link. Todo con la del propio sistema."
    : "A este teléfono le falta criptografía que necesita el Link (pide iOS 17+ o un Android con WebView actualizado). No se va a emparejar con algo más débil.";
}

/** Human words for what went wrong. */
export function explain(error: unknown): string {
  if (error instanceof LinkClientError) {
    if (error.code === "rejected") return "Tu PC no aceptó la petición. Si acabas de enlazar, revisa que escribiste el código correcto en la PC.";
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

/** One line of the activity feed / receipts list for a phone receipt. */
export function describeReceipt(r: PhoneReceipt): string {
  switch (r.kind) {
    case "link_paired": return `PC enlazada · ${r.name}`;
    case "link_delegated": return `Tarea enviada · ${r.title ?? r.task_id ?? ""} → ${r.name}`;
    case "link_cancelled": return `Tarea cancelada · ${r.task_id ?? ""} en ${r.name}`;
    case "link_forgotten": return `PC olvidada · ${r.name}`;
    case "link_permission_approved": return `Permiso aprobado · ${r.capability ?? ""} en ${r.name}`;
    case "link_permission_denied": return `Permiso rechazado · ${r.capability ?? ""} en ${r.name}`;
    case "link_permission_expired": return `Permiso vencido · ${r.capability ?? ""} en ${r.name}`;
  }
}

const STATE_LABEL: Record<PetState, string> = { idle: "en reposo", thinking: "preguntando a tu PC…", working: "tu PC está trabajando", waiting: "esperándote", success: "respuesta firmada", error: "algo no salió" };
const STATE_COLOR: Record<PetState, string> = { idle: "var(--signal)", thinking: "#e0d36a", working: "#5fb3ff", waiting: "#c9a7ff", success: "var(--ok)", error: "var(--deny)" };
/** Signed frames fade like the desktop avatar's verdicts. */
const FRAME_TTL_MS = 8000;

const ICON = {
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
  tasks: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg>',
  permissions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3 20 6v5c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6z"/><path d="m8.5 12 2.3 2.3 4.8-5"/></svg>',
  receipts: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6"/></svg>',
  phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/></svg>',
  pc: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/></svg>',
  mark: '<svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 28 9v14l-12 7L4 23V9z" fill="none" stroke="var(--signal)" stroke-width="2.4"/><path d="M16 9v14M11 12l5-3 5 3M11 20l5 3 5-3" stroke="var(--signal)" stroke-width="2.4" fill="none" stroke-linecap="round"/></svg>',
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label: string, className: string, onClick: () => void | Promise<void>): HTMLButtonElement {
  const b = el("button", className, label);
  b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await onClick();
    } finally {
      b.disabled = false;
    }
  });
  return b;
}

const clock = (iso: string) => new Date(iso).toTimeString().slice(0, 5);

export interface AppDeps {
  root: HTMLElement;
  kv: KeyValue;
  identity: () => Promise<LinkIdentity>;
  support: Promise<CryptoSupport>;
  fetch: Fetch;
  gus?: GusAppDeps;
}

type Tab = "home" | "tasks" | "permissions" | "receipts" | "phone";
interface Signed { host: string; line: string; detail: string; at: number }

export function startApp(deps: AppDeps): void {
  const { root, kv } = deps;
  let support: CryptoSupport | null = null;
  let mood: PetState = "idle";
  let moodTimer = 0;
  let signed: Signed | null = null;
  let pet: ReturnType<typeof createPet> | null = null;
  let chip: { dot: HTMLElement; label: HTMLElement } | null = null;
  let frameEl: HTMLElement | null = null;
  let gusUnsubscribe: (() => void) | null = null;
  const gus: GusChatController = createGusChat(deps.gus ?? {
    local: null, remote: null, catalogue: GUS_MODELS, models: null,
    secureStore: {
      async getRemoteConfig() { return null; }, async getApiKey() { return null; },
      async saveRemoteConfig() { throw new Error("La configuración remota requiere almacenamiento seguro nativo."); },
      async saveApiKey() { throw new Error("La llave remota requiere almacenamiento seguro nativo."); },
      async clearRemoteConfig() { throw new Error("La configuración remota requiere almacenamiento seguro nativo."); },
    },
  });
  void deps.support.then((s) => (support = s));

  /** What the app is doing, shown by Malbolgato and the status chip. */
  function setMood(state: PetState, ms = 0, then: PetState = "idle"): void {
    mood = state;
    pet?.setState(state);
    if (chip) {
      chip.label.textContent = STATE_LABEL[state];
      chip.dot.style.background = STATE_COLOR[state];
      chip.dot.style.boxShadow = `0 0 8px ${STATE_COLOR[state]}`;
    }
    clearTimeout(moodTimer);
    if (ms) moodTimer = window.setTimeout(() => setMood(then), ms);
  }
  /** Only for replies that came back sealed by the paired PC (the client checks that). */
  function showSigned(host: string, line: string, detail: string): void {
    signed = { host, line, detail, at: Date.now() };
    renderFrame();
  }
  function renderFrame(): void {
    if (!frameEl) return;
    const fresh = signed && Date.now() - signed.at < FRAME_TTL_MS ? signed : null;
    frameEl.className = fresh ? "frame" : "frame empty";
    frameEl.replaceChildren();
    if (!fresh) {
      frameEl.append(el("span", "k", "Marco de autoridad"), el("span", undefined, "Sin respuestas firmadas recientes. Solo tus PCs pueden escribir aquí."));
      return;
    }
    const bar = el("span", "ttl");
    frameEl.append(el("span", "k", `[ ${fresh.host} ] · firmado por la PC`), el("span", undefined, `FIRMADO · ${fresh.line}`), el("span", "d", fresh.detail), bar);
    const left = FRAME_TTL_MS - (Date.now() - fresh.at);
    bar.animate?.([{ width: `${(left / FRAME_TTL_MS) * 100}%` }, { width: "0%" }], { duration: left, easing: "linear" });
    window.setTimeout(renderFrame, left + 20);
  }

  function layout(content: HTMLElement[], tab: Tab | null): void {
    gusUnsubscribe?.(); gusUnsubscribe = null;
    pet?.destroy();
    pet = null;
    chip = null;
    frameEl = null;
    const app = el("div", "app");
    const screen = el("main", "screen");
    screen.append(...content);
    app.append(screen);
    if (tab) {
      const bar = el("nav", "tabbar");
      bar.setAttribute("aria-label", "Secciones");
      const tabs: Array<[Tab, string, string]> = [["home", "Inicio", ICON.home], ["tasks", "Tareas", ICON.tasks], ["permissions", "Permisos", ICON.permissions], ["receipts", "Recibos", ICON.receipts], ["phone", "Teléfono", ICON.phone]];
      for (const [id, label, icon] of tabs) {
        const b = el("button", id === tab ? "on" : "");
        b.type = "button";
        b.innerHTML = `${icon}<span>${label}</span>`;
        if (id === tab) b.setAttribute("aria-current", "page");
        b.addEventListener("click", () => go(id));
        bar.append(b);
      }
      app.append(bar);
    }
    root.replaceChildren(app);
  }

  function go(tab: Tab): void {
    if (tab === "home") home();
    if (tab === "tasks") tasksScreen();
    if (tab === "permissions") permissionsScreen();
    if (tab === "receipts") receiptsScreen();
    if (tab === "phone") phoneScreen();
  }

  let lastProfile: string | null = null;
  let lastSessionUntil: string | null = null;

  async function doPing(peer: Peer): Promise<boolean> {
    setMood("thinking");
    pet?.say(`Preguntándole a ${peer.name}…`, 1400);
    try {
      const reply = await ping(await deps.identity(), peer, deps.fetch);
      lastProfile = (reply?.tool_profile as string | null | undefined) ?? null;
      lastSessionUntil = (reply?.session_until as string | null | undefined) ?? null;
      setMood("success", 1800);
      showSigned(peer.name, "pong", `respuesta sellada y atada a la petición · ${new Date().toTimeString().slice(0, 5)}`);
      return true;
    } catch (error) {
      setMood("error", 2400);
      pet?.say(explain(error), 3200);
      return false;
    }
  }

  function sessionBadge(): string {
    if (!lastSessionUntil) return "Sesión: aún no validada";
    const when = new Date(lastSessionUntil);
    const now = new Date();
    if (when.getTime() + 60000 < now.getTime()) return `Sesión expirada (${when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} UTC renueva con ping)`;
    return `Sesión activa hasta ${when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }

  function profileBadge(): string {
    if (!lastProfile) return "Perfil de herramientas: desconocido (haz ping)";
    if (lastProfile === "full") return "Perfil de tools: FULL ⚠ testing/no recomendado";
    if (lastProfile === "custom") return "Perfil de tools: CUSTOM";
    return "Perfil de tools: SECURITY";
  }

  // ---------------------------------------------------------------- Inicio
  function home(): void {
    const peers = Object.values(loadPeers(kv));
    const appbar = el("header", "appbar");
    const brand = el("div", "brand");
    brand.innerHTML = `${ICON.mark}<span>ISYMOTRON</span>`;
    appbar.append(brand);

    const hero = el("section", "hero");
    const left = el("div");
    const dot = el("i");
    const label = el("span", undefined, STATE_LABEL[mood]);
    const chipEl = el("div", "state-chip");
    chipEl.setAttribute("aria-live", "polite");
    chipEl.append(dot, label);
    left.append(el("div", "eyebrow", "Autoridad local"), el("h1", undefined, "Tu teléfono pide. Tu PC decide."), el("p", undefined, "Malbolgato te muestra lo que tus PCs deciden. Él no decide nada."), chipEl);
    const wrap = el("div", "pet-wrap");
    wrap.append(el("div", "pedestal"));
    hero.append(left, wrap, el("span", "hint-corner", "toca · arrastra · mantén"));

    const frame = el("div", "frame empty");
    frame.setAttribute("aria-live", "polite");

    const pcs = el("div", "list");
    for (const peer of peers) {
      const row = el("div", "pc");
      const ico = el("div", "ico");
      ico.innerHTML = ICON.pc;
      const open = el("button", "row-btn");
      open.type = "button";
      open.append(el("b", undefined, peer.name), el("small", undefined, `${prettyFingerprint(peer.office_id).slice(0, 9)} · ${peer.addresses[0] ?? ""}`));
      open.addEventListener("click", () => peerScreen(peer));
      row.append(ico, open, button("ping", "ping", async () => void (await doPing(peer))));
      pcs.append(row);
    }
    const pair = button(peers.length ? "Enlazar otra PC" : "Enlazar con mi PC", "btn primary", () => pairScreen());
    if (support && !canPair(support)) pair.disabled = true;
    const openGus = button("Abrir GUS · asistente", "btn gus-entry", () => gusScreen());

    const feed = el("div", "feed");
    const recent = loadReceipts(kv).slice(-4).reverse();
    if (!recent.length) feed.append(el("p", "hint small", "Aquí verás lo que pasa con tus PCs."));
    for (const r of recent) {
      const row = el("div");
      row.append(el("time", undefined, clock(r.at)), el("span", undefined, describeReceipt(r)));
      feed.append(row);
    }

    layout([
      appbar,
      hero,
      frame,
      (() => { const s = el("div", "sec"); s.append(el("h2", undefined, "Mis PCs"), el("span", peers.length ? "pill" : "pill off", peers.length ? `${peers.length} enlazada${peers.length > 1 ? "s" : ""}` : "ninguna")); return s; })(),
      ...(peers.length ? [pcs] : [el("p", "hint", "Todavía no enlazas ninguna PC.")]),
      pair,
      openGus,
      (() => { const s = el("div", "sec"); s.append(el("h2", undefined, "Actividad")); return s; })(),
      feed,
    ], "home");

    chip = { dot, label };
    frameEl = frame;
    pet = createPet(wrap, { stage: hero, onHold: () => controls(peers) });
    setMood(mood);
    renderFrame();
    void deps.support.then((s) => { if (!canPair(s)) { pair.disabled = true; pet?.say("Este teléfono no tiene la criptografía del Link.", 4000); } });
  }

  // --------------------------------------------------------------- GUS
  function gusScreen(): void {
    const state = gus.getState();
    const top = button("‹ Inicio", "back", () => home());
    const modeRow = el("div", "gus-modes");
    const localMode = button("En este teléfono", "btn small", () => gus.selectMode("local"));
    const remoteMode = button("Proveedor remoto", "btn small", () => gus.selectMode("remote"));
    const modeHint = el("p", "hint small");
    const modelList = el("div", "gus-models");
    const status = el("p", "gus-status"); status.setAttribute("aria-live", "polite");
    const transcript = el("div", "gus-transcript"); transcript.setAttribute("aria-label", "Conversación con GUS");
    const prompt = el("textarea", "field gus-prompt"); prompt.rows = 2; prompt.maxLength = 12000; prompt.placeholder = "Pregúntale algo a GUS"; prompt.setAttribute("aria-label", "Mensaje para GUS");
    const composer = el("form", "gus-composer");
    const send = el("button", "btn primary small", "Enviar"); send.type = "submit";
    const stop = button("Cancelar respuesta", "btn small", () => void gus.cancel());
    const clear = button("Borrar conversación", "btn small", () => gus.clearSession());
    const remotePanel = el("section", "card gus-remote");
    const endpoint = el("input", "field"); endpoint.type = "url"; endpoint.autocomplete = "off"; endpoint.setAttribute("aria-label", "URL HTTPS del proveedor remoto"); endpoint.placeholder = "https://integrate.api.nvidia.com/v1";
    const modelName = el("input", "field"); modelName.autocomplete = "off"; modelName.setAttribute("aria-label", "Nombre del modelo remoto"); modelName.placeholder = "nvidia/nemotron-3-nano-30b-a3b";
    const apiKey = el("input", "field"); apiKey.type = "password"; apiKey.autocomplete = "new-password"; apiKey.setAttribute("aria-label", "API key del proveedor remoto"); apiKey.placeholder = "Pega aquí tu API key";
    const saved = el("p", "hint small", "La API key solo se guarda en el almacén seguro del sistema."); saved.setAttribute("aria-live", "polite");
    const nim = button("Usar preset NVIDIA NIM", "btn small", () => {
      endpoint.value = NVIDIA_NIM_PRESET.baseUrl;
      modelName.value = NVIDIA_NIM_PRESET.model;
      gus.selectMode("remote");
      renderState(gus.getState());
    });
    const saveRemote = button("Guardar configuración y API key", "btn", async () => {
      await gus.saveRemoteConfig({ baseUrl: endpoint.value.trim(), model: modelName.value.trim() });
      if (gus.getState().error) { saved.textContent = gus.getState().error; return; }
      if (apiKey.value) { await gus.saveApiKey(apiKey.value); apiKey.value = ""; }
      saved.textContent = gus.getState().error || gus.getState().notice;
      renderState(gus.getState());
    });
    remotePanel.append(el("h2", undefined, "Conexión remota"), nim,
      el("label", "gus-label", "URL HTTPS"), endpoint,
      el("label", "gus-label", "Modelo"), modelName,
      el("label", "gus-label", "API key (se guarda en Keychain/Keystore)"), apiKey,
      el("div", "warnbox", "Al elegir modo remoto, tu mensaje y contexto se envían al proveedor seleccionado. No se manda nada hasta que selecciones remoto y envíes."), saveRemote, saved);
    composer.append(prompt, send);

    function renderModels(): void {
      const current = gus.getState();
      modelList.replaceChildren();
      for (const model of GUS_MODELS) {
        const installed = current.installedModelIds.includes(model.id);
        const card = el("article", "gus-model");
        const pick = button(model.name, current.selectedModelId === model.id ? "btn small selected" : "btn small", () => { gus.selectModel(model.id); renderState(gus.getState()); });
        card.append(pick, el("p", "hint small", `${(model.byteCount / 1_000_000_000).toFixed(2)} GB · ${model.repository} · ${model.licenseName}`), el("p", "hint small", model.attribution), el("a", "gus-license", "Ver licencia"));
        const link = card.querySelector("a") as HTMLAnchorElement; link.href = model.licenseUrl; link.target = "_blank"; link.rel = "noreferrer";
        if (model.limitations?.length) {
          const limits = el("ul", "gus-limitations");
          for (const limitation of model.limitations) limits.append(el("li", undefined, limitation));
          card.append(limits);
        }
        if (deps.gus?.models) {
          card.append(installed ? el("span", "pill", "verificado e instalado") : button("Descargar y verificar", "btn small", () => void gus.downloadModel(model.id)));
          if (installed) card.append(button("Guardar copia externa", "btn small", () => void gus.exportModel(model.id)));
          if (current.progress?.modelId === model.id) card.append(button("Cancelar descarga", "btn small", () => void gus.cancelDownload(model.id)));
        } else card.append(el("p", "hint small", "Instala la app nativa para descargar, importar o ejecutar modelos locales."));
        modelList.append(card);
      }
    }

    function renderState(next: ReturnType<GusChatController["getState"]>): void {
      localMode.classList.toggle("selected", next.mode === "local"); remoteMode.classList.toggle("selected", next.mode === "remote");
      localMode.setAttribute("aria-pressed", String(next.mode === "local")); remoteMode.setAttribute("aria-pressed", String(next.mode === "remote"));
      modeHint.textContent = next.mode === "local"
        ? deps.gus?.local ? "Modo local: el modelo seleccionado se ejecuta en este teléfono." : "Modo local seleccionado. En navegador no hay runtime; la app no enviará nada a la nube."
        : "Modo remoto seleccionado. Solo se enviarán mensajes cuando pulses Enviar.";
      status.textContent = next.error || next.notice || (next.loading ? "GUS está respondiendo…" : "");
      status.className = next.error ? "gus-status error" : "gus-status";
      send.disabled = next.loading;
      stop.disabled = !next.loading;
      transcript.replaceChildren();
      for (const message of next.messages) {
        const bubble = el("p", `gus-message ${message.role}`, message.content);
        transcript.append(bubble);
      }
      if (next.progress) {
        const mb = (next.progress.receivedBytes / 1_000_000).toFixed(0);
        const total = next.progress.totalBytes ? ` / ${(next.progress.totalBytes / 1_000_000).toFixed(0)} MB` : "";
        status.textContent = `Descargando modelo: ${mb}${total}`;
      }
      renderModels();
    }

    modeRow.setAttribute("role", "group"); modeRow.setAttribute("aria-label", "Modo de inferencia");
    modeRow.append(localMode, remoteMode);
    const isyCard = el("section", "card gus-isymotron");
    isyCard.append(
      el("div", "eyebrow", "GUS ISYMOTRON"),
      el("p", "hint small", "GUS te ayuda a formular; la PC recibe la tarea por Link, la decide, la ejecuta y deja recibo. GUS nunca toca Link, permisos ni archivos por su cuenta."),
      button("Mandar el último mensaje a mi PC", "btn", async () => {
        const peer = Object.values(loadPeers(kv))[0];
        if (!peer) { status.textContent = "Enlaza una PC primero (Inicio → Enlazar con mi PC)."; return; }
        const composed = composeDelegateFromMessages(gus.getState().messages);
        if (!composed) { status.textContent = "Escribe primero un mensaje para GUS."; return; }
        status.textContent = "Delegando…";
        try {
          const reply = await delegate(await deps.identity(), peer, composed.title, composed.body, deps.fetch);
          addReceipt(kv, { kind: "link_delegated", office_id: peer.office_id, name: peer.name, task_id: String(reply.task_id), title: composed.title });
          status.textContent = `✓ Tarea en la bandeja de ${peer.name} (${String(reply.task_id)}). Sigue su estado en Tareas.`;
        } catch (error) { status.textContent = explain(error); }
      }),
    );
    composer.addEventListener("submit", (event) => {
      event.preventDefault(); const value = prompt.value; prompt.value = ""; void gus.send(value);
    });
    layout([
      top, el("div", "eyebrow", "Orientación · GUS no decide"), el("h1", undefined, "GUS"),
      el("p", "hint small", "GUS solo conversa. No puede usar tus permisos, leer archivos ni mandar tareas a tus PCs. Para delegar una tarea en tu PC usa la tarjeta GUS ISYMOTRON de abajo."),
      modeRow, modeHint,
      el("h2", undefined, "Modelos locales verificados"), modelList,
      ...(deps.gus?.models ? [button("Importar copia guardada con iSyCode", "btn small", () => void gus.importModels())] : []),
      remotePanel, transcript, status, composer, stop, clear,
      isyCard,
    ], null);
    gusUnsubscribe = gus.subscribe(renderState);
    renderState(state);
    void gus.refreshModels();
    void deps.gus?.secureStore.getRemoteConfig().then((config) => { if (config) { endpoint.value = config.baseUrl; modelName.value = config.model; } }).catch(() => {});
    prompt.focus();
  }

  /** Long press on Malbolgato: his controls, like the desktop pet's right click. */
  function controls(peers: Peer[]): void {
    const scrim = el("div", "scrim");
    const sheet = el("div", "sheet");
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-label", "Controles de Malbolgato");
    const close = () => scrim.remove();
    const item = (label: string, hint: string, act: () => void) => {
      const b = el("button");
      b.type = "button";
      b.append(document.createTextNode(label), el("span", undefined, hint));
      b.addEventListener("click", () => { close(); act(); });
      return b;
    };
    sheet.append(el("div", "grab"));
    const first = peers[0];
    if (first) {
      sheet.append(item("Probar conexión", first.name, () => void doPing(first)));
      sheet.append(item("Mandar una tarea", first.name, () => peerScreen(first)));
    }
    sheet.append(item(first ? "Enlazar otra PC" : "Enlazar con mi PC", "código de 6 dígitos", () => pairScreen()));
    sheet.append(item("Jugar", "corre por la tarjeta", () => pet?.run()));
    sheet.append(item("Cerrar", "", () => {}));
    scrim.append(sheet);
    scrim.addEventListener("click", (e) => { if (e.target === scrim) close(); });
    scrim.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    root.querySelector(".app")?.append(scrim);
    (sheet.querySelector("button") as HTMLButtonElement | null)?.focus();
  }

  // ---------------------------------------------------------------- Enlazar
  function steps(n: number): HTMLElement {
    const s = el("div", "steps");
    for (let i = 1; i <= 3; i++) s.append(el("i", i <= n ? "on" : ""));
    return s;
  }

  function pairScreen(): void {
    const input = el("input", "field addr");
    input.id = "pc-address";
    input.placeholder = "192.168.1.20:47931";
    input.inputMode = "url";
    input.autocomplete = "off";
    input.setAttribute("aria-label", "Dirección de tu PC");
    const out = el("p", "hint");
    out.setAttribute("aria-live", "polite");
    const one = el("p", "hint");
    one.innerHTML = '<span class="n">1</span>En tu PC corre:';
    const two = el("p", "hint");
    two.innerHTML = '<span class="n">2</span>Escribe aquí la dirección que te muestra («En el teléfono escribe: …»).';
    layout([
      button("‹ Inicio", "back", () => home()),
      steps(2),
      el("div", "eyebrow", "Enlazar con mi PC"),
      el("h1", undefined, "¿Dónde está tu PC?"),
      one,
      el("pre", "cmd", "isymotron link servir --red"),
      two,
      input,
      el("p", "hint small", "El teléfono y la PC tienen que estar en la misma Wi-Fi. Si Windows pregunta por el firewall, permite redes privadas."),
      button("Pedir enlace", "btn primary", async () => {
        out.textContent = "Buscando tu PC…";
        setMood("thinking");
        try {
          const address = parseAddress(input.value);
          const proposal = await requestPairing(await deps.identity(), address, deps.fetch);
          setMood("waiting");
          codeScreen(proposal);
        } catch (error) {
          setMood("error", 2400);
          out.textContent = explain(error);
        }
      }),
      out,
    ], null);
    input.focus();
  }

  function codeScreen(p: PairingProposal): void {
    const out = el("p", "hint");
    out.setAttribute("aria-live", "polite");
    const code = el("p", "code");
    code.setAttribute("aria-label", `Código ${spacedCode(p.code)}`);
    [...p.code].forEach((d, i) => { if (i === 3) code.append(el("span", "gap")); code.append(el("span", undefined, d)); });
    const pc = el("div", "pc");
    const ico = el("div", "ico");
    ico.innerHTML = ICON.pc;
    const who = el("div", "row-btn");
    who.append(el("b", undefined, p.peer.name), el("small", undefined, `huella ${prettyFingerprint(p.peer.office_id)}`));
    pc.append(ico, who);
    layout([
      button("‹ Dirección", "back", () => pairScreen()),
      steps(3),
      pc,
      el("div", "eyebrow", "Escribe este código en tu PC"),
      code,
      el("pre", "cmd", `isymotron link aceptar ${p.code}`),
      el("div", "warnbox", "Si tu PC dice que el código no coincide, no sigas: alguien más podría estar en medio."),
      button("Ya lo escribí en mi PC", "btn primary", async () => {
        out.textContent = "Comprobando con tu PC…";
        setMood("thinking");
        try {
          const own = await deps.identity();
          await ping(own, p.peer, deps.fetch); // only a reply sealed by this PC counts
          const pinned = trustPeer(kv, p.peer);
          addReceipt(kv, { kind: "link_paired", office_id: pinned.office_id, name: pinned.name });
          setMood("success", 2000);
          showSigned(pinned.name, "enlazada", `huella ${prettyFingerprint(pinned.office_id)}`);
          peerScreen(pinned, `✓ Enlazado con ${pinned.name}. Su respuesta llegó firmada por ella.`);
        } catch (error) {
          setMood("waiting");
          out.textContent = explain(error);
        }
      }),
      out,
      button("Cancelar", "btn", () => { setMood("idle"); home(); }),
    ], null);
  }

  // ---------------------------------------------------------------- tasks (shared by Mi PC and Tareas)
  function taskList(filter: (r: PhoneReceipt) => boolean, peers: Record<string, Peer>): HTMLElement {
    const box = el("div", "list");
    const mine = loadReceipts(kv).filter((r) => r.kind === "link_delegated" && filter(r)).reverse();
    if (!mine.length) box.append(el("p", "hint small", "Todavía no hay tareas."));
    for (const r of mine) {
      const peer = peers[r.office_id];
      const row = el("div", "task");
      const status = el("span", "hint small", "");
      row.append(el("strong", undefined, r.title ?? r.task_id ?? "tarea"), el("span", "hint small", `${r.name} · ${clock(r.at)}`), status);
      if (peer) {
        row.append(
          button("Ver estado", "btn small", async () => {
            try {
              const reply = await task(await deps.identity(), peer, String(r.task_id), deps.fetch);
              status.textContent = ` · ${String((reply.task as { status?: string } | undefined)?.status ?? "?")}`;
            } catch (error) {
              status.textContent = ` · ${explain(error)}`;
            }
          }),
          button("Cancelar", "btn small", async () => {
            try {
              await cancel(await deps.identity(), peer, String(r.task_id), deps.fetch);
              addReceipt(kv, { kind: "link_cancelled", office_id: peer.office_id, name: peer.name, task_id: r.task_id });
              status.textContent = " · cancelled";
            } catch (error) {
              status.textContent = ` · ${explain(error)}`;
            }
          }),
        );
      }
      box.append(row);
    }
    return box;
  }

  function peerScreen(peer: Peer, notice = ""): void {
    // Opening the PC card refreshes the Link session window so the badge
    // "Sesión activa" is what the human sees first, not a stale one.
    if (!lastProfile || !lastSessionUntil) void doPing(peer);
    const out = el("p", "hint", notice);
    out.setAttribute("aria-live", "polite");
    const title = el("input", "field");
    title.id = "task-title";
    title.placeholder = "Qué quieres que haga tu PC";
    title.maxLength = 120;
    title.setAttribute("aria-label", "Título de la tarea");
    const body = el("textarea", "field");
    body.id = "task-body";
    body.placeholder = "Detalles (opcional)";
    body.maxLength = 4000;
    body.rows = 3;
    body.setAttribute("aria-label", "Detalles de la tarea");
    const tasks = el("div");
    const refresh = () => tasks.replaceChildren(taskList((r) => r.office_id === peer.office_id, { [peer.office_id]: peer }));
    refresh();
    const compose = el("section", "card");
    compose.append(
      el("div", "eyebrow", "Mandar una tarea"),
      el("p", "hint small", "La tarea cae en la bandeja de tu PC; ahí se decide qué hacer con ella."),
      title,
      body,
      button("Mandar a mi PC", "btn primary", async () => {
        if (!title.value.trim()) return void (out.textContent = "Escribe qué quieres que haga.");
        setMood("working");
        try {
          const reply = await delegate(await deps.identity(), peer, title.value.trim(), body.value.trim(), deps.fetch);
          addReceipt(kv, { kind: "link_delegated", office_id: peer.office_id, name: peer.name, task_id: String(reply.task_id), title: title.value.trim() });
          setMood("success", 1800);
          showSigned(peer.name, "tarea en bandeja", `«${title.value.trim()}» · ${String(reply.task_id)}`);
          out.textContent = `✓ Tarea en la bandeja de ${peer.name} (${String(reply.task_id)}).`;
          title.value = "";
          body.value = "";
          refresh();
        } catch (error) {
          setMood("error", 2400);
          out.textContent = explain(error);
        }
      }),
    );
    layout([
      button("‹ Mis PCs", "back", () => home()),
      el("h1", undefined, peer.name),
      el("p", "hint small", `Huella ${prettyFingerprint(peer.office_id)} · ${peer.addresses.join(", ")}`),
      el("p", "hint small", profileBadge()),
      el("p", "hint small", sessionBadge()),
      button("Probar conexión", "btn", async () => {
        out.textContent = "Llamando…";
        out.textContent = (await doPing(peer)) ? `✓ ${peer.name} contestó, con su firma.` : "No contestó. Revisa la Wi-Fi y que corra «isymotron link servir --red».";
      }),
      out,
      compose,
      el("h2", undefined, "Tareas que le mandé"),
      tasks,
      button("Olvidar esta PC", "btn danger", () => {
        if (!globalThis.confirm?.(`¿Olvidar ${peer.name}? Tendrás que enlazarla otra vez.`)) return;
        forgetPeer(kv, peer.office_id);
        addReceipt(kv, { kind: "link_forgotten", office_id: peer.office_id, name: peer.name });
        home();
      }),
      button("Volver", "btn", () => home()),
    ], "home");
  }

  // ---------------------------------------------------------------- Tareas, Recibos, Teléfono
  function tasksScreen(): void {
    layout([el("div", "eyebrow", "Todas tus PCs"), el("h1", undefined, "Tareas"), taskList(() => true, loadPeers(kv))], "tasks");
  }

  function permissionCard(peer: Peer, request: PermissionRequest, notice: HTMLElement, refresh: () => Promise<void>): HTMLElement {
    const card = el("section", "card permission-card");
    card.append(
      el("div", "eyebrow", peer.name),
      el("h2", undefined, request.capability),
      el("p", "hint small", `Solicitado por ${request.subject} · hasta ${request.ttl_s} s`),
      el("p", "hint small", `Alcance solicitado: ${JSON.stringify(request.scope)}`),
      el("p", "hint", request.reason || "Esta solicitud no incluyó un motivo."),
    );
    const actions = el("div", "sec");
    for (const choice of ["approve", "deny"] as const) {
      actions.append(button(
        choice === "approve" ? "Sí, aprobar" : "No, rechazar",
        choice === "approve" ? "btn primary" : "btn danger",
        async () => {
          notice.textContent = "La PC está decidiendo…";
          try {
            const result = await decidePermission(
              await deps.identity(), peer, request.request_id, choice, deps.fetch,
            );
            const approved = result.status === "approved";
            addReceipt(kv, {
              kind: approved ? "link_permission_approved" : result.status === "expired" ? "link_permission_expired" : "link_permission_denied",
              office_id: peer.office_id,
              name: peer.name,
              request_id: request.request_id,
              capability: request.capability,
            });
            setMood(approved ? "success" : "waiting", 1800);
            showSigned(peer.name, approved ? "permiso aprobado" : "permiso rechazado", `${request.capability} · ${request.request_id}`);
            const outcome = approved
              ? `Permiso aprobado por ${peer.name}. La PC emitió el lease dentro de sus límites.`
              : result.status === "expired"
                ? `La solicitud de ${peer.name} venció antes de decidirse.`
                : `Permiso rechazado por ${peer.name}.`;
            await refresh();
            notice.textContent = outcome;
          } catch (error) {
            setMood("error", 2400);
            notice.textContent = explain(error);
          }
        },
      ));
    }
    card.append(actions);
    return card;
  }

  function permissionsScreen(): void {
    const notice = el("p", "hint", "Revisando permisos…");
    notice.setAttribute("aria-live", "polite");
    const rows = el("div", "list");
    const peers = Object.values(loadPeers(kv));
    layout([
      el("div", "eyebrow", "La PC conserva la autoridad"),
      el("h1", undefined, "Permisos pendientes"),
      el("p", "hint small", "Tú respondes sí o no. La PC comprueba sus permisos locales y emite el lease."),
      notice,
      rows,
      button("Actualizar", "btn", async () => refresh()),
    ], "permissions");

    async function refresh(): Promise<void> {
      rows.replaceChildren();
      if (!peers.length) {
        notice.textContent = "Enlaza una PC para revisar sus permisos pendientes.";
        return;
      }
      notice.textContent = "Revisando permisos…";
      const own = await deps.identity();
      let pendingCount = 0;
      const failures: string[] = [];
      for (const peer of peers) {
        try {
          const response = await listPermissions(own, peer, deps.fetch);
          for (const request of response.requests) {
            rows.append(permissionCard(peer, request, notice, refresh));
            pendingCount += 1;
          }
        } catch (error) {
          failures.push(`${peer.name}: ${explain(error)}`);
        }
      }
      if (failures.length) notice.textContent = failures.join(" · ");
      else if (!pendingCount) notice.textContent = "No hay permisos pendientes.";
      else notice.textContent = `${pendingCount} solicitud${pendingCount === 1 ? "" : "es"} esperando tu decisión.`;
    }
    void refresh().catch((error) => { notice.textContent = explain(error); });
  }

  function receiptsScreen(): void {
    const feed = el("div", "feed");
    const all = loadReceipts(kv).slice().reverse();
    if (!all.length) feed.append(el("p", "hint", "Todavía no hay recibos. Se crean al enlazar una PC y al mandarle tareas."));
    for (const r of all) {
      const row = el("div");
      row.append(el("time", undefined, `${r.at.slice(5, 10)} ${clock(r.at)}`), el("span", undefined, describeReceipt(r)));
      feed.append(row);
    }
    layout([el("div", "eyebrow", "Historial de este teléfono"), el("h1", undefined, "Recibos"), el("p", "hint small", "Lo que este teléfono hizo. Lo que decidió cada PC queda en los recibos de esa PC."), feed], "receipts");
  }

  function phoneScreen(): void {
    const id = el("section", "card");
    const fp = el("div", "fp", "…");
    const who = el("p", "hint small", "");
    id.append(el("div", "eyebrow", "Tu huella"), fp, who, el("p", "hint small", "Tus PCs ven esta huella con «isymotron link estado»."));
    const crypto = el("section", "card");
    const checks = el("ul", "checks");
    const verdict = el("p", "hint small", "Revisando la criptografía de este teléfono…");
    crypto.append(el("div", "eyebrow", "Criptografía del sistema"), checks, verdict, el("p", "hint small", "Las llaves privadas no se pueden copiar ni exportar, ni siquiera por esta app."));
    layout([el("div", "eyebrow", "Identidad"), el("h1", undefined, "Este teléfono"), id, crypto], "phone");
    void deps.support.then(async (s) => {
      checks.replaceChildren(...supportLines(s).map((line) => el("li", undefined, line)));
      verdict.textContent = supportVerdict(s);
      if (!canPair(s)) return void (fp.textContent = "sin identidad");
      const own = await deps.identity();
      fp.textContent = prettyFingerprint(own.officeId);
      who.textContent = `${own.name} · creada el ${own.createdAt.slice(0, 10)}`;
    });
  }

  home();
}
