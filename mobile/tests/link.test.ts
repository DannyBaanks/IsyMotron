import { readFileSync } from "node:fs";
import { b64u, unb64u } from "../src/link/bytes";
import { EnvelopeError, openEnvelope, seal, type Envelope, type Peer } from "../src/link/envelope";
import { generateKeys, identityFromKeys, publicCard, shortCode, type LinkIdentity } from "../src/link/identity";

const V = JSON.parse(readFileSync(new URL("./fixtures/link-vectors.json", import.meta.url), "utf8"));
type PcIdentity = { name: string; office_id: string; sign: { x: string; d: string }; box: { x: string; d: string } };

/** Test keys from the vectors, imported as JWK (x + d). The app itself only ever generates keys. */
async function load(id: PcIdentity): Promise<LinkIdentity> {
  const s = crypto.subtle;
  const sign = {
    privateKey: await s.importKey("jwk", { kty: "OKP", crv: "Ed25519", x: id.sign.x, d: id.sign.d }, { name: "Ed25519" }, false, ["sign"]),
    publicKey: await s.importKey("raw", unb64u(id.sign.x), { name: "Ed25519" }, true, ["verify"]),
  };
  const box = {
    privateKey: await s.importKey("jwk", { kty: "OKP", crv: "X25519", x: id.box.x, d: id.box.d }, { name: "X25519" }, false, ["deriveBits"]),
    publicKey: await s.importKey("raw", unb64u(id.box.x), { name: "X25519" }, true, []),
  };
  return identityFromKeys(id.name, sign, box);
}

const asPeer = (id: PcIdentity): Peer => ({ office_id: id.office_id, name: id.name, sign_pub: id.sign.x, box_pub: id.box.x, addresses: [] });

describe("Link identity matches the PC", () => {
  it("office_id, public card and the 6-digit code are the same as the PC computes", async () => {
    const phone = await load(V.phone);
    expect(phone.officeId).toBe(V.phone.office_id);
    expect(publicCard(phone)).toEqual({ protocol: "isymotron-link@1", office_id: V.phone.office_id, name: V.phone.name, sign_pub: V.phone.sign.x, box_pub: V.phone.box.x });
    const code = await shortCode(V.phone.sign.x, V.pc.sign.x, V.short_code.nonce_phone, V.short_code.nonce_pc);
    expect(code).toBe(V.short_code.code);
    // order-independent, like the PC
    expect(await shortCode(V.pc.sign.x, V.phone.sign.x, V.short_code.nonce_pc, V.short_code.nonce_phone)).toBe(code);
  });

  it("generated private keys cannot be exported", async () => {
    const { sign, box } = await generateKeys();
    await expect(crypto.subtle.exportKey("jwk", sign.privateKey)).rejects.toThrow();
    await expect(crypto.subtle.exportKey("jwk", box.privateKey)).rejects.toThrow();
    const id = await identityFromKeys("isytron-x", sign, box);
    expect(id.officeId).toMatch(/^[0-9a-f]{16}$/);
    expect(JSON.stringify(publicCard(id))).not.toMatch(/"d"/);
  });
});

describe("sealed envelopes are byte-identical to the PC's", () => {
  it("the phone seals exactly what the PC's code seals for the same keys and randomness", async () => {
    const phone = await load(V.phone);
    const v = V.phone_to_pc;
    const env = await seal(phone, asPeer(V.pc), v.payload, { now: v.now * 1000, iv: unb64u(v.iv), nonce: unb64u(v.nonce) });
    expect(env).toEqual(v.env);
  });

  it("the PC's HKDF key decrypts what the phone sealed (same key derivation)", async () => {
    const phone = await load(V.phone);
    const v = V.phone_to_pc;
    const env = await seal(phone, asPeer(V.pc), v.payload, { now: v.now * 1000 });
    const hexKey = Uint8Array.from(V.shared_key_hex.match(/../g).map((h: string) => parseInt(h, 16)));
    const key = await crypto.subtle.importKey("raw", hexKey, "AES-GCM", false, ["decrypt"]);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64u(env.iv), additionalData: new TextEncoder().encode(`${V.phone.office_id}>${V.pc.office_id}`) }, key, unb64u(env.ct));
    expect(JSON.parse(new TextDecoder().decode(plain))).toEqual(v.payload);
  });

  it("the phone opens what the PC sealed", async () => {
    const phone = await load(V.phone);
    const v = V.pc_to_phone;
    const { peer, payload } = await openEnvelope(phone, { [V.pc.office_id]: asPeer(V.pc) }, v.env, new Map(), v.now * 1000);
    expect(peer.office_id).toBe(V.pc.office_id);
    expect(payload).toEqual(v.payload);
  });
});

describe("opening is fail-closed", () => {
  const ctx = async () => ({ phone: await load(V.phone), peers: { [V.pc.office_id]: asPeer(V.pc) }, env: V.pc_to_phone.env as Envelope, now: V.pc_to_phone.now * 1000 });

  it("unknown sender, wrong recipient, tampering, stale time and replay are all rejected", async () => {
    const { phone, peers, env, now } = await ctx();
    const reject = (e: Envelope, p = peers, seen = new Map<string, number>(), t = now) => expect(openEnvelope(phone, p, e, seen, t)).rejects.toBeInstanceOf(EnvelopeError);
    await reject(env, {});
    await reject({ ...env, to: "0000000000000000" });
    const ct = unb64u(env.ct);
    ct[0] = ct[0]! ^ 1;
    await reject({ ...env, ct: b64u(ct) });
    await reject({ ...env, ts: env.ts + 1 });
    await reject(env, peers, new Map(), now + 121_000);
    const seen = new Map<string, number>();
    await openEnvelope(phone, peers, env, seen, now);
    await reject(env, peers, seen);
  });
});

import { loadOrCreateIdentity, memoryKeyStore } from "../src/link/keystore";

describe("the phone keeps one identity", () => {
  it("is created once and then always the same office_id", async () => {
    const store = memoryKeyStore();
    const first = await loadOrCreateIdentity(store, "isytron-mi-telefono");
    const again = await loadOrCreateIdentity(store, "otro-nombre");
    expect(again.officeId).toBe(first.officeId);
    expect(again.name).toBe("isytron-mi-telefono");
    expect((await store.get())!.sign.privateKey.extractable).toBe(false);
    expect((await store.get())!.box.privateKey.extractable).toBe(false);
  });
});
