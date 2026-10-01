/**
 * The app's screens. Version 1: pair with an IsyMotron PC over Link (code on both sides),
 * then ping it, hand it a task, follow and cancel that task. The PC decides everything; the
 * phone only asks, shows sealed answers and keeps its own receipts.
 */
import { cancel, delegate, LinkClientError, parseAddress, ping, requestPairing, task, type Fetch, type PairingProposal } from "./link/client";
import type { Peer } from "./link/envelope";
import { prettyFingerprint, type LinkIdentity } from "./link/identity";
import { addReceipt, forgetPeer, loadPeers, loadReceipts, spacedCode, trustPeer, type KeyValue } from "./store";
import { canPair, type CryptoSupport } from "./support";

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

export interface AppDeps {
  root: HTMLElement;
  kv: KeyValue;
  identity: () => Promise<LinkIdentity>;
  support: Promise<CryptoSupport>;
  fetch: Fetch;
}

export function startApp(deps: AppDeps): void {
  const { root, kv } = deps;
  let support: CryptoSupport | null = null;

  const header = () => {
    const h = el("header", "top");
    h.append(el("p", "kicker", "IsyMotron"), el("h1", undefined, "Tu teléfono, tu PC, tus reglas"));
    h.append(el("p", "lead", "El modelo propone, tu PC decide y queda un recibo. Este teléfono es tu mano: pide y aprueba, nunca manda por su cuenta."));
    return h;
  };

  function home(): void {
    const peers = Object.values(loadPeers(kv));
    const pcs = el("section", "card");
    pcs.append(el("h2", undefined, "Mis PCs"));
    if (!peers.length) pcs.append(el("p", "hint", "Todavía no enlazas ninguna PC."));
    const list = el("div", "list");
    for (const peer of peers) {
      const row = button(`${peer.name}  ›`, "row-btn", () => peerScreen(peer));
      list.append(row);
    }
    pcs.append(list);
    const pair = button("Enlazar con mi PC", "btn primary", () => pairScreen());
    pair.disabled = support !== null && !canPair(support);
    pcs.append(pair);

    const crypto = el("section", "card");
    const checks = el("ul", "checks");
    const verdict = el("p", "hint", "Revisando la criptografía de este teléfono…");
    crypto.append(el("h2", undefined, "Este teléfono"), checks, verdict);
    void deps.support.then((s) => {
      support = s;
      checks.replaceChildren(...supportLines(s).map((line) => el("li", undefined, line)));
      verdict.textContent = supportVerdict(s);
      pair.disabled = !canPair(s);
    });
    root.replaceChildren(header(), pcs, crypto);
  }

  function pairScreen(): void {
    const card = el("section", "card");
    const input = el("input", "field");
    input.placeholder = "192.168.1.20:47931";
    input.inputMode = "url";
    input.autocomplete = "off";
    input.setAttribute("aria-label", "Dirección de tu PC");
    const out = el("p", "hint");
    out.setAttribute("aria-live", "polite");
    card.append(
      el("h2", undefined, "Enlazar con mi PC"),
      el("p", "hint", "1. En tu PC corre:"),
      el("pre", "cmd", "isymotron link servir --red"),
      el("p", "hint", "2. Escribe aquí la dirección que te muestra («En el teléfono escribe: …»)."),
      input,
      button("Pedir enlace", "btn primary", async () => {
        out.textContent = "Buscando tu PC…";
        try {
          const address = parseAddress(input.value);
          const proposal = await requestPairing(await deps.identity(), address, deps.fetch);
          codeScreen(proposal);
        } catch (error) {
          out.textContent = explain(error);
        }
      }),
      out,
      button("Volver", "btn", () => home()),
    );
    root.replaceChildren(header(), card);
    input.focus();
  }

  function codeScreen(p: PairingProposal): void {
    const card = el("section", "card");
    const out = el("p", "hint");
    out.setAttribute("aria-live", "polite");
    card.append(
      el("h2", undefined, `Tu PC: ${p.peer.name}`),
      el("p", "hint small", `Huella: ${prettyFingerprint(p.peer.office_id)}`),
      el("p", "hint", "3. En tu PC escribe:"),
      el("pre", "cmd", `isymotron link aceptar ${p.code}`),
      el("p", "code", spacedCode(p.code)),
      el("p", "hint small", "Si la PC dice que el código no coincide, no sigas: alguien más podría estar en medio."),
      button("Ya lo escribí en mi PC", "btn primary", async () => {
        out.textContent = "Comprobando con tu PC…";
        try {
          const own = await deps.identity();
          await ping(own, p.peer, deps.fetch); // only a reply sealed by this PC counts
          const pinned = trustPeer(kv, p.peer);
          addReceipt(kv, { kind: "link_paired", office_id: pinned.office_id, name: pinned.name });
          peerScreen(pinned, `✓ Enlazado con ${pinned.name}. Su respuesta llegó firmada por ella.`);
        } catch (error) {
          out.textContent = explain(error);
        }
      }),
      out,
      button("Cancelar", "btn", () => home()),
    );
    root.replaceChildren(header(), card);
  }

  function peerScreen(peer: Peer, notice = ""): void {
    const card = el("section", "card");
    const out = el("p", "hint", notice);
    out.setAttribute("aria-live", "polite");
    const title = el("input", "field");
    title.placeholder = "Qué quieres que haga tu PC";
    title.maxLength = 120;
    title.setAttribute("aria-label", "Título de la tarea");
    const body = el("textarea", "field");
    body.placeholder = "Detalles (opcional)";
    body.maxLength = 4000;
    body.rows = 3;
    body.setAttribute("aria-label", "Detalles de la tarea");

    const tasks = el("div", "list");
    const renderTasks = () => {
      const mine = loadReceipts(kv).filter((r) => r.kind === "link_delegated" && r.office_id === peer.office_id).reverse();
      tasks.replaceChildren(...(mine.length ? [] : [el("p", "hint small", "Todavía no le mandas tareas.")]));
      for (const r of mine) {
        const row = el("div", "task");
        const status = el("span", "hint small", "");
        row.append(
          el("strong", undefined, r.title ?? r.task_id ?? "tarea"),
          status,
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
        tasks.append(row);
      }
    };
    renderTasks();

    card.append(
      el("h2", undefined, peer.name),
      el("p", "hint small", `Huella: ${prettyFingerprint(peer.office_id)} · ${peer.addresses.join(", ")}`),
      button("Probar conexión", "btn", async () => {
        out.textContent = "Llamando…";
        try {
          await ping(await deps.identity(), peer, deps.fetch);
          out.textContent = `✓ ${peer.name} contestó, con su firma.`;
        } catch (error) {
          out.textContent = explain(error);
        }
      }),
      out,
      el("h3", undefined, "Mandar una tarea"),
      el("p", "hint small", "La tarea cae en la bandeja de tu PC; ahí se decide qué hacer con ella."),
      title,
      body,
      button("Mandar a mi PC", "btn primary", async () => {
        if (!title.value.trim()) return void (out.textContent = "Escribe qué quieres que haga.");
        try {
          const reply = await delegate(await deps.identity(), peer, title.value.trim(), body.value.trim(), deps.fetch);
          addReceipt(kv, { kind: "link_delegated", office_id: peer.office_id, name: peer.name, task_id: String(reply.task_id), title: title.value.trim() });
          out.textContent = `✓ Tarea en la bandeja de ${peer.name} (${String(reply.task_id)}).`;
          title.value = "";
          body.value = "";
          renderTasks();
        } catch (error) {
          out.textContent = explain(error);
        }
      }),
      el("h3", undefined, "Tareas que le mandé"),
      tasks,
      button("Olvidar esta PC", "btn danger", () => {
        if (!globalThis.confirm?.(`¿Olvidar ${peer.name}? Tendrás que enlazarla otra vez.`)) return;
        forgetPeer(kv, peer.office_id);
        addReceipt(kv, { kind: "link_forgotten", office_id: peer.office_id, name: peer.name });
        home();
      }),
      button("Volver", "btn", () => home()),
    );
    root.replaceChildren(header(), card);
  }

  home();
}
