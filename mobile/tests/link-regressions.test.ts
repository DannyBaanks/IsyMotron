import { readFileSync } from "node:fs";
import { parseAddress } from "../src/link/client";
import { openEnvelope, type Envelope, type Peer } from "../src/link/envelope";
import { unb64u } from "../src/link/bytes";
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

describe("Link regression gates", () => {
  it("drops expired reply nonces before remembering a fresh one", async () => {
    const phone = await load(V.phone);
    const env = V.pc_to_phone.env as Envelope;
    const now = V.pc_to_phone.now * 1000;
    const seen = new Map<string, number>([["expired-a", now - 1], ["expired-b", now - 10]]);

    await openEnvelope(phone, { [V.pc.office_id]: asPeer(V.pc) }, env, seen, now);

    expect([...seen.keys()]).toEqual([env.nonce]);
  });

  it("allows LAN, mDNS and Tailscale addresses but rejects public cleartext targets", () => {
    for (const address of [
      "192.168.1.20:47931",
      "10.0.0.5:47931",
      "172.16.0.1:47931",
      "169.254.1.2:47931",
      "127.0.0.1:47931",
      "100.64.1.2:47931",
      "pc.local:47931",
      "pc:47931",
      "pc.tailnet.ts.net:47931",
      "[fd7a:115c:a1e0::1]:47931",
      "[fe80::1]:47931",
    ]) expect(parseAddress(address)).toBe(address);

    for (const address of [
      "8.8.8.8:47931",
      "1.1.1.1:47931",
      "172.15.0.1:47931",
      "172.32.0.1:47931",
      "100.63.255.255:47931",
      "100.128.0.1:47931",
      "example.com:47931",
      "https://192.168.1.20:47931",
    ]) expect(() => parseAddress(address)).toThrow();
  });
});
