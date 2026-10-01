/**
 * The phone's Link identity, wire-compatible with the PC (core/isymotron/link/identity.py):
 * an Ed25519 key to sign, an X25519 key to agree on secrets, and an office_id that is the
 * first 16 hex of SHA-256(signing public key). Only the platform's WebCrypto is used, and
 * the private keys are created non-extractable: no code path can read or export them.
 */
import { b64u, hex, utf8 } from "./bytes";

export const PROTOCOL = "isymotron-link@1";

export interface LinkIdentity {
  protocol: typeof PROTOCOL;
  name: string;
  officeId: string;
  signPub: string;
  boxPub: string;
  signKey: CryptoKey;
  boxKey: CryptoKey;
  createdAt: string;
}

/** What anyone may learn about us. Same field names as the PC's public_card. */
export interface PublicCard {
  protocol: string;
  office_id: string;
  name: string;
  sign_pub: string;
  box_pub: string;
}

export async function officeIdOf(signPubRaw: Uint8Array<ArrayBuffer>, subtle: SubtleCrypto = crypto.subtle): Promise<string> {
  return hex(await subtle.digest("SHA-256", signPubRaw)).slice(0, 16);
}

/** From existing keys (generated here, or loaded from the key store). */
export async function identityFromKeys(
  name: string,
  sign: CryptoKeyPair,
  box: CryptoKeyPair,
  createdAt = new Date().toISOString(),
  subtle: SubtleCrypto = crypto.subtle,
): Promise<LinkIdentity> {
  const signRaw = new Uint8Array(await subtle.exportKey("raw", sign.publicKey));
  const boxRaw = new Uint8Array(await subtle.exportKey("raw", box.publicKey));
  return {
    protocol: PROTOCOL,
    name,
    officeId: await officeIdOf(signRaw, subtle),
    signPub: b64u(signRaw),
    boxPub: b64u(boxRaw),
    signKey: sign.privateKey,
    boxKey: box.privateKey,
    createdAt,
  };
}

export async function generateKeys(subtle: SubtleCrypto = crypto.subtle): Promise<{ sign: CryptoKeyPair; box: CryptoKeyPair }> {
  const sign = (await subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"])) as CryptoKeyPair;
  const box = (await subtle.generateKey({ name: "X25519" }, false, ["deriveBits"])) as CryptoKeyPair;
  return { sign, box };
}

export function publicCard(id: LinkIdentity): PublicCard {
  return { protocol: PROTOCOL, office_id: id.officeId, name: id.name, sign_pub: id.signPub, box_pub: id.boxPub };
}

export function prettyFingerprint(officeId: string): string {
  return officeId.match(/.{1,4}/g)?.join(" ") ?? officeId;
}

/** The phone's office name, like the PC's `isytron-<host>`. */
export function defaultName(device = "telefono"): string {
  const clean = device.toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 24);
  return `isytron-${clean || "telefono"}`;
}

export function freshNonce(): string {
  return b64u(crypto.getRandomValues(new Uint8Array(16)));
}

/**
 * The 6 digits both humans compare (link/pairing.py `short_code`). Order-independent: keys
 * and nonces are each sorted, so a man in the middle cannot make both screens agree.
 */
export async function shortCode(signPubA: string, signPubB: string, nonceA: string, nonceB: string, subtle: SubtleCrypto = crypto.subtle): Promise<string> {
  const keys = [signPubA, signPubB].sort();
  const nonces = [nonceA, nonceB].sort();
  const digest = new Uint8Array(await subtle.digest("SHA-256", utf8([PROTOCOL, ...keys, ...nonces].join("|"))));
  const n = ((digest[0]! << 24) >>> 0) + (digest[1]! << 16) + (digest[2]! << 8) + digest[3]!;
  return String(n % 1_000_000).padStart(6, "0");
}
