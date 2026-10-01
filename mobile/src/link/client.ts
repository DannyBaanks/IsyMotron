/**
 * The phone talking to an IsyMotron PC's Link server (core/isymotron/link/server.py).
 * Pairing never trusts anything by itself: it returns the 6-digit code, and the peer is only
 * remembered after the human confirms the same code is on the PC's screen.
 */
import { hex, unb64u } from "./bytes";
import { openEnvelope, seal, type Envelope, type Peer } from "./envelope";
import { PROTOCOL, freshNonce, publicCard, shortCode, type LinkIdentity, type PublicCard } from "./identity";

export type Fetch = (url: string, init?: { method?: string; headers?: Record<string, string>; body?: string; signal?: AbortSignal }) => Promise<{ status: number; json(): Promise<unknown> }>;

export class LinkClientError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

function privateIpv4(host: string): boolean {
  const octets = host.split(".");
  if (octets.length !== 4) return false;
  const nums = octets.map((part) => Number(part));
  if (nums.some((n, i) => !Number.isInteger(n) || n < 0 || n > 255 || String(n) !== octets[i])) return false;
  const [a, b] = nums;
  return a === 10 || a === 127 || (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) ||
    (a === 100 && b >= 64 && b <= 127); // RFC 6598, used by Tailscale
}

function localHost(host: string): boolean {
  const value = host.toLowerCase();
  if (privateIpv4(value)) return true;
  if (value.startsWith("[") && value.endsWith("]")) {
    const ip = value.slice(1, -1);
    if (ip === "::1") return true;
    const first = Number.parseInt(ip.split(":", 1)[0] ?? "", 16);
    return (first >= 0xfc00 && first <= 0xfdff) || (first >= 0xfe80 && first <= 0xfebf);
  }
  return value === "localhost" || !value.includes(".") || value.endsWith(".local") || value.endsWith(".ts.net");
}

/** Local/Tailscale host:port only. No paths and no arbitrary public cleartext destination. */
export function parseAddress(text: string): string {
  const value = text.trim().replace(/^http:\/\//, "").replace(/\/+$/, "");
  const m = /^([A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\]):(\d{1,5})$/.exec(value);
  const port = m ? Number(m[2]) : 0;
  if (!m || port < 1 || port > 65535 || !localHost(m[1])) {
    throw new LinkClientError("bad_address", "Escribe una dirección local o de Tailscale como IP:puerto, por ejemplo 192.168.1.20:47931.");
  }
  return `${m[1]}:${port}`;
}

async function postJson(fetchFn: Fetch, url: string, body: unknown, timeoutMs: number): Promise<{ status: number; body: Record<string, unknown> }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchFn(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal });
    const parsed = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    return { status: res.status, body: parsed && typeof parsed === "object" ? parsed : {} };
  } catch {
    throw new LinkClientError("unreachable", "No encontré la PC en esa dirección. ¿Están en la misma Wi-Fi y corre «isymotron link servir --red»?");
  } finally {
    clearTimeout(timer);
  }
}

async function cardIsSelfConsistent(card: PublicCard): Promise<boolean> {
  try {
    return hex(await crypto.subtle.digest("SHA-256", unb64u(card.sign_pub))).slice(0, 16) === card.office_id;
  } catch {
    return false;
  }
}

export interface PairingProposal {
  /** Not trusted yet: only after the human confirms the code. */
  peer: Peer;
  code: string;
  expiresAt: number;
}

export async function requestPairing(own: LinkIdentity, address: string, fetchFn: Fetch, timeoutMs = 15_000): Promise<PairingProposal> {
  const safeAddress = parseAddress(address);
  const nonce = freshNonce();
  const { status, body } = await postJson(fetchFn, `http://${safeAddress}/link/v1/pair`, { ...publicCard(own), nonce, port: 0 }, timeoutMs);
  if (status !== 200 || body.ok !== true) throw new LinkClientError(String(body.code ?? `http_${status}`), `La PC rechazó el emparejamiento: ${String(body.error ?? body.code ?? status)}`);
  const card = body.peer as PublicCard | undefined;
  const peerNonce = body.nonce;
  if (!card || typeof peerNonce !== "string" || card.protocol !== PROTOCOL || !(await cardIsSelfConsistent(card))) {
    throw new LinkClientError("bad_identity", "La PC respondió con una identidad que no cuadra. No se emparejó.");
  }
  if (card.office_id === own.officeId) throw new LinkClientError("self", "Esa dirección es este mismo teléfono.");
  return {
    peer: { office_id: card.office_id, name: String(card.name).slice(0, 64), sign_pub: card.sign_pub, box_pub: card.box_pub, addresses: [safeAddress] },
    code: await shortCode(own.signPub, card.sign_pub, nonce, peerNonce),
    expiresAt: Number(body.expires_at ?? 0) * 1000,
  };
}

/** Reply nonces already accepted (anti-replay for sealed replies, per app run). */
const seenReplies = new Map<string, number>();

/**
 * One sealed operation to a paired PC. The request is signed and encrypted, and the only
 * reply the phone believes is the PC's sealed one (`renv`): signed by the paired PC, sealed
 * to this phone and bound to this request's nonce. The plain JSON beside it is ignored, so
 * someone else on the network cannot fake an answer.
 */
export async function call(own: LinkIdentity, peer: Peer, payload: Record<string, unknown>, fetchFn: Fetch, timeoutMs = 15_000): Promise<Record<string, unknown>> {
  let last: LinkClientError = new LinkClientError("unreachable", `Sin dirección para ${peer.name}.`);
  for (const rawAddress of peer.addresses) {
    let address: string;
    try {
      address = parseAddress(rawAddress);
    } catch (error) {
      last = error instanceof LinkClientError ? error : new LinkClientError("bad_address", String(error));
      continue;
    }
    const env = await seal(own, peer, payload);
    try {
      const { status, body } = await postJson(fetchFn, `http://${address}/link/v1/call`, { env }, timeoutMs);
      if (status === 200 && body.ok === true) return await trustedReply(own, peer, env, body);
      last = new LinkClientError(String(body.code ?? `http_${status}`), String(body.error ?? body.code ?? `HTTP ${status}`));
    } catch (error) {
      last = error instanceof LinkClientError ? error : new LinkClientError("unreachable", String(error));
    }
  }
  throw last;
}

async function trustedReply(own: LinkIdentity, peer: Peer, request: Envelope, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (!body.renv || typeof body.renv !== "object") {
    throw new LinkClientError("unsealed_reply", "Tu PC respondió sin firmar. Actualiza IsyMotron en la PC (necesita respuestas selladas).");
  }
  let reply: Record<string, unknown>;
  try {
    reply = (await openEnvelope(own, { [peer.office_id]: peer }, body.renv as Envelope, seenReplies)).payload;
  } catch (error) {
    throw new LinkClientError("bad_reply", `La respuesta no viene de ${peer.name}: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (reply.re !== request.nonce) throw new LinkClientError("bad_reply", "La respuesta no corresponde a esta petición.");
  const { re: _re, ...result } = reply;
  return result;
}

export const ping = (own: LinkIdentity, peer: Peer, f: Fetch) => call(own, peer, { op: "ping" }, f);
export const delegate = (own: LinkIdentity, peer: Peer, title: string, body: string, f: Fetch) => call(own, peer, { op: "delegate", title, body }, f);
export const task = (own: LinkIdentity, peer: Peer, taskId: string, f: Fetch) => call(own, peer, { op: "task", task_id: taskId }, f);
export const cancel = (own: LinkIdentity, peer: Peer, taskId: string, f: Fetch) => call(own, peer, { op: "cancel", task_id: taskId }, f);
