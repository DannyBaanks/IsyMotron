/**
 * First screen. Version 1 of the app pairs the phone with an IsyMotron PC over Link; until
 * that lands (roadmap M4) the screen shows what the phone can already do, honestly.
 */
import { canPair, cryptoSupport, type CryptoSupport } from "./support";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function supportLines(s: CryptoSupport): string[] {
  const mark = (ok: boolean) => (ok ? "✓" : "✗");
  return [
    `${mark(s.ed25519)} Firmas Ed25519`,
    `${mark(s.x25519)} Llaves X25519`,
    `${mark(s.hkdf)} HKDF-SHA256`,
    `${mark(s.aesGcm)} AES-GCM`,
  ];
}

export function supportVerdict(s: CryptoSupport): string {
  return canPair(s)
    ? "Este teléfono tiene la criptografía que necesita el Link. Todo con la del propio sistema."
    : "A este teléfono le falta criptografía que necesita el Link (pide iOS 17+ o un Android con WebView actualizado). No se va a emparejar con algo más débil.";
}

export function renderHome(root: HTMLElement): void {
  const header = el("header", "top");
  header.append(el("p", "kicker", "IsyMotron"), el("h1", undefined, "Tu teléfono, tu PC, tus reglas"));
  header.append(el("p", "lead", "El modelo propone, tu PC decide y queda un recibo. Este teléfono es tu mano: pide y aprueba, nunca manda por su cuenta."));

  const pcs = el("section", "card");
  pcs.append(el("h2", undefined, "Mis PCs"), el("p", "hint", "Todavía no enlazas ninguna PC."));
  const pair = el("button", "btn primary", "Enlazar con mi PC");
  pair.disabled = true;
  pcs.append(pair, el("p", "hint small", "Muy pronto: en tu PC corre «isymotron link servir --red», escribe aquí su dirección y comparan el código de 6 dígitos."));

  const crypto = el("section", "card");
  const list = el("ul", "checks");
  const verdict = el("p", "hint", "Revisando la criptografía de este teléfono…");
  crypto.append(el("h2", undefined, "Este teléfono"), list, verdict);

  root.replaceChildren(header, pcs, crypto);

  void cryptoSupport().then((s) => {
    list.replaceChildren(...supportLines(s).map((line) => el("li", undefined, line)));
    verdict.textContent = supportVerdict(s);
  });
}
