import "./styles.css";
import { startApp } from "./home";
import { indexedDbKeyStore, loadOrCreateIdentity } from "./link/keystore";
import type { LinkIdentity } from "./link/identity";
import { cryptoSupport } from "./support";

let identity: Promise<LinkIdentity> | null = null;

startApp({
  root: document.getElementById("app")!,
  kv: localStorage,
  // Created on first use, so a phone without the crypto never makes a half identity.
  identity: () => (identity ??= loadOrCreateIdentity(indexedDbKeyStore())),
  support: cryptoSupport(),
  // In the native app CapacitorHttp routes this through native HTTP (no CORS).
  fetch: (url, init) => fetch(url, init),
});
