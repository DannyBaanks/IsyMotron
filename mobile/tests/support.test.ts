import { canPair, cryptoSupport } from "../src/support";
import { supportLines, supportVerdict } from "../src/home";

describe("platform crypto probe", () => {
  it("Node 22's WebCrypto has everything the Link needs (the same API the phone's WebView exposes)", async () => {
    const s = await cryptoSupport();
    expect(s).toEqual({ ed25519: true, x25519: true, aesGcm: true, hkdf: true });
    expect(canPair(s)).toBe(true);
  });

  it("no WebCrypto means no pairing, never a weaker fallback", async () => {
    const s = await cryptoSupport(null);
    expect(canPair(s)).toBe(false);
  });

  it("a platform missing one primitive cannot pair, and the screen says why", async () => {
    const real = globalThis.crypto.subtle;
    const noEd = new Proxy(real, {
      get(target, prop) {
        if (prop === "generateKey") {
          return (alg: AlgorithmIdentifier, ...rest: unknown[]) =>
            (alg as { name?: string }).name === "Ed25519" ? Promise.reject(new Error("NotSupportedError")) : (target.generateKey as Function).call(target, alg, ...rest);
        }
        const v = Reflect.get(target, prop);
        return typeof v === "function" ? v.bind(target) : v;
      },
    });
    const s = await cryptoSupport(noEd);
    expect(s.ed25519).toBe(false);
    expect(s.x25519).toBe(true);
    expect(canPair(s)).toBe(false);
    expect(supportLines(s)[0]).toBe("✗ Firmas Ed25519");
    expect(supportVerdict(s)).toMatch(/No se va a emparejar/);
  });
});
