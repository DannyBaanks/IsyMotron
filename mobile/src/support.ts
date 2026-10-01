/**
 * What this phone's own crypto can do. The Link needs Ed25519 (signatures) and X25519
 * (key agreement) from the platform: the app never ships its own primitives. If either is
 * missing the app says so and does not pair, instead of falling back to something weaker.
 */
export interface CryptoSupport {
  ed25519: boolean;
  x25519: boolean;
  aesGcm: boolean;
  hkdf: boolean;
}

export const canPair = (s: CryptoSupport): boolean => s.ed25519 && s.x25519 && s.aesGcm && s.hkdf;

async function works(probe: () => Promise<unknown>): Promise<boolean> {
  try {
    await probe();
    return true;
  } catch {
    return false;
  }
}

/** Probes by doing the real operation once, not by reading a feature list. */
export async function cryptoSupport(subtle: SubtleCrypto | null = globalThis.crypto?.subtle ?? null): Promise<CryptoSupport> {
  if (!subtle) return { ed25519: false, x25519: false, aesGcm: false, hkdf: false };
  const data = new TextEncoder().encode("isymotron-link@1 probe");
  const ed25519 = await works(async () => {
    const pair = (await subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"])) as CryptoKeyPair;
    const sig = await subtle.sign({ name: "Ed25519" }, pair.privateKey, data);
    if (!(await subtle.verify({ name: "Ed25519" }, pair.publicKey, sig, data))) throw new Error("verify");
  });
  const x25519 = await works(async () => {
    const a = (await subtle.generateKey({ name: "X25519" }, false, ["deriveBits"])) as CryptoKeyPair;
    const b = (await subtle.generateKey({ name: "X25519" }, false, ["deriveBits"])) as CryptoKeyPair;
    await subtle.deriveBits({ name: "X25519", public: b.publicKey }, a.privateKey, 256);
  });
  const aesGcm = await works(async () => {
    const key = await subtle.generateKey({ name: "AES-GCM", length: 128 }, false, ["encrypt"]);
    await subtle.encrypt({ name: "AES-GCM", iv: new Uint8Array(12) }, key, data);
  });
  const hkdf = await works(async () => {
    const base = await subtle.importKey("raw", new Uint8Array(32), "HKDF", false, ["deriveBits"]);
    await subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: data }, base, 128);
  });
  return { ed25519, x25519, aesGcm, hkdf };
}
