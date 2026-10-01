/**
 * Sealed envelopes, byte-compatible with the PC (core/isymotron/link/envelope.py):
 * X25519 → HKDF-SHA256(salt = sorted office ids, info "isymotron-link@1 seal", 16 bytes)
 * → AES-128-GCM with AAD "from>to", plus an Ed25519 signature over "v|from|to|ts|nonce|iv|ct".
 * Opening is fail-closed: unknown sender, wrong recipient, bad signature, stale time or a
 * replayed nonce all throw before anything is decrypted or trusted.
 */
import { b64u, concat, unb64u, utf8 } from "./bytes";
import { PROTOCOL, type LinkIdentity } from "./identity";

export const MAX_SKEW_MS = 120_000;
export const NONCE_TTL_MS = 600_000;

export interface Envelope {
  v: 1;
  from: string;
  to: string;
  ts: number;
  nonce: string;
  iv: string;
  ct: string;
  sig: string;
}

/** A paired office as the phone remembers it (the PC's peers.json entry). */
export interface Peer {
  office_id: string;
  name: string;
  sign_pub: string;
  box_pub: string;
  addresses: string[];
  paired_at?: string;
}

export class EnvelopeError extends Error {}

export async function sharedKey(own: LinkIdentity, peerBoxPub: string, peerOfficeId: string, subtle: SubtleCrypto = crypto.subtle): Promise<CryptoKey> {
  const peerKey = await subtle.importKey("raw", unb64u(peerBoxPub), { name: "X25519" }, false, []);
  const secret = await subtle.deriveBits({ name: "X25519", public: peerKey }, own.boxKey, 256);
  const base = await subtle.importKey("raw", secret, "HKDF", false, ["deriveBits"]);
  const salt = utf8([own.officeId, peerOfficeId].sort().join("|"));
  const bits = await subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info: utf8(`${PROTOCOL} seal`) }, base, 128);
  return subtle.importKey("raw", bits, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

const signedText = (e: Omit<Envelope, "sig">): Uint8Array<ArrayBuffer> => utf8([e.v, e.from, e.to, e.ts, e.nonce, e.iv, e.ct].join("|"));

export interface SealOptions {
  now?: number;
  /** Tests only: fixed IV and nonce to compare bytes with the PC. */
  iv?: Uint8Array<ArrayBuffer>;
  nonce?: Uint8Array<ArrayBuffer>;
  subtle?: SubtleCrypto;
}

export async function seal(own: LinkIdentity, peer: Pick<Peer, "office_id" | "box_pub">, payload: Record<string, unknown>, options: SealOptions = {}): Promise<Envelope> {
  const subtle = options.subtle ?? crypto.subtle;
  const key = await sharedKey(own, peer.box_pub, peer.office_id, subtle);
  const iv = options.iv ?? crypto.getRandomValues(new Uint8Array(12));
  const aad = utf8(`${own.officeId}>${peer.office_id}`);
  const body = utf8(JSON.stringify(payload));
  const ct = new Uint8Array(await subtle.encrypt({ name: "AES-GCM", iv, additionalData: aad }, key, body)); // ciphertext ‖ 16-byte tag, as on the PC
  const unsigned = {
    v: 1 as const,
    from: own.officeId,
    to: peer.office_id,
    ts: Math.floor(options.now ?? Date.now()),
    nonce: b64u(options.nonce ?? crypto.getRandomValues(new Uint8Array(16))),
    iv: b64u(iv),
    ct: b64u(ct),
  };
  const sig = await subtle.sign({ name: "Ed25519" }, own.signKey, signedText(unsigned));
  return { ...unsigned, sig: b64u(sig) };
}

export async function openEnvelope(
  own: LinkIdentity,
  peers: Record<string, Peer>,
  env: Envelope,
  seenNonces: Map<string, number>,
  now = Date.now(),
  subtle: SubtleCrypto = crypto.subtle,
): Promise<{ peer: Peer; payload: Record<string, unknown> }> {
  for (const field of ["v", "from", "to", "ts", "nonce", "iv", "ct", "sig"] as const) {
    if (!(field in env)) throw new EnvelopeError(`missing field ${field}`);
  }
  if (env.v !== 1) throw new EnvelopeError(`unsupported envelope v${String(env.v)}`);
  const peer = peers[String(env.from)];
  if (!peer) throw new EnvelopeError("unknown office (not paired)");
  if (String(env.to) !== own.officeId) throw new EnvelopeError("envelope not addressed to us");
  let ok = false;
  try {
    const signKey = await subtle.importKey("raw", unb64u(peer.sign_pub), { name: "Ed25519" }, false, ["verify"]);
    ok = await subtle.verify({ name: "Ed25519" }, signKey, unb64u(env.sig), signedText(env));
  } catch {
    ok = false;
  }
  if (!ok) throw new EnvelopeError("bad signature");
  if (Math.abs(now - Number(env.ts)) > MAX_SKEW_MS) throw new EnvelopeError("envelope outside time window");
  for (const [oldNonce, oldExpiry] of seenNonces) {
    if (oldExpiry <= now) seenNonces.delete(oldNonce);
  }
  const expiry = seenNonces.get(env.nonce);
  if (expiry !== undefined && expiry > now) throw new EnvelopeError("nonce replay");
  seenNonces.set(env.nonce, now + NONCE_TTL_MS);
  let payload: unknown;
  try {
    const key = await sharedKey(own, peer.box_pub, peer.office_id, subtle);
    const plain = await subtle.decrypt(
      { name: "AES-GCM", iv: unb64u(env.iv), additionalData: utf8(`${peer.office_id}>${own.officeId}`) },
      key,
      unb64u(env.ct),
    );
    payload = JSON.parse(new TextDecoder().decode(plain));
  } catch (error) {
    throw new EnvelopeError(`cannot open: ${error instanceof Error ? error.name : "error"}`);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new EnvelopeError("payload must be an object");
  return { peer, payload: payload as Record<string, unknown> };
}
