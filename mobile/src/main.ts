import "@fontsource/chakra-petch/600.css";
import "@fontsource/chakra-petch/700.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "@fontsource/jetbrains-mono/700.css";
import "./styles.css";
import { startApp } from "./home";
import { indexedDbKeyStore, loadOrCreateIdentity } from "./link/keystore";
import type { LinkIdentity } from "./link/identity";
import { cryptoSupport } from "./support";

let identity: Promise<LinkIdentity> | null = null;

async function boot(): Promise<void> {
  const e2eGus = import.meta.env.MODE === "e2e" ? await import("./gus/e2e-mock") : null;
  const gus = e2eGus?.e2eMockGus ?? (async () => {
    const [{ nativeGus }, { GUS_MODELS }] = await Promise.all([import("./gus/native"), import("./gus/catalog.generated")]);
    return { local: nativeGus.local, secureStore: nativeGus.secureStore, models: nativeGus.models, catalogue: GUS_MODELS };
  });
  startApp({
    root: document.getElementById("app")!,
    kv: localStorage,
    // Created on first use, so a phone without the crypto never makes a half identity.
    identity: () => (identity ??= loadOrCreateIdentity(indexedDbKeyStore())),
    support: cryptoSupport(),
    // In the native app CapacitorHttp routes this through native HTTP (no CORS).
    fetch: (url, init) => fetch(url, init),
    gus,
  });
}

void boot();
