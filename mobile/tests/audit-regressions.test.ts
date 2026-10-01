import { readFileSync } from "node:fs";
import { unb64u } from "../src/link/bytes";
import { parseAddress } from "../src/link/client";
import { openEnvelope, type Envelope, type Peer } from "../src/link/envelope";
import { identityFromKeys, type LinkIdentity } from "../src/link/identity";

const V = JSON.parse(readFileSync(new URL("./fixtures/link-vectors.json", import.meta.url), "utf8"));
type PcIdentity = { name: string; office_id: string; sign: { x: string; d: string }; box: { x: string; d: string } };

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

const asPeer = (id: PcIdentity): Peer => ({
  office_id: id.office_id,
  name: id.name,
  sign_pub: id.sign.x,
  box_pub: id.box.x,
  addresses: [],
});

describe("Link audit regressions", () => {
  it("prunes expired reply nonces before remembering a fresh one", async () => {
    const phone = await load(V.phone);
    const env = V.pc_to_phone.env as Envelope;
    const now = V.pc_to_phone.now * 1000;
    const seen = new Map<string, number>([
      ["expired-a", now - 10],
      ["expired-b", now],
    ]);

    await openEnvelope(phone, { [V.pc.office_id]: asPeer(V.pc) }, env, seen, now);

    expect([...seen.keys()]).toEqual([env.nonce]);
  });

  it("accepts only local-network cleartext destinations", () => {
    for (const good of [
      "192.168.1.20:47931",
      "10.20.30.40:47931",
      "172.16.0.1:47931",
      "172.31.255.254:47931",
      "127.0.0.1:47931",
      "169.254.4.2:47931",
      "http://pc.local:47931/",
      "[::1]:47931",
      "[fd12:3456::1]:47931",
      "[fe80::1234]:47931",
    ]) {
      expect(() => parseAddress(good)).not.toThrow();
    }

    for (const bad of [
      "8.8.8.8:47931",
      "1.1.1.1:47931",
      "172.32.0.1:47931",
      "203.0.113.10:47931",
      "example.com:47931",
      "api.openai.com:47931",
      "999.999.999.999:47931",
      "https://pc.local:47931",
    ]) {
      expect(() => parseAddress(bad)).toThrow();
    }
  });
});
