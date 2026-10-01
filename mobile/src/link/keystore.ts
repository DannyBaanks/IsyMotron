/**
 * Where the phone keeps its Link identity. The private keys are non-extractable CryptoKeys:
 * IndexedDB stores the key objects themselves (structured clone), never their bytes, so
 * not even this app can read them back out. Lost storage means a new identity and pairing
 * again, never a weaker key.
 */
import { defaultName, generateKeys, identityFromKeys, type LinkIdentity } from "./identity";

export interface StoredIdentity {
  name: string;
  createdAt: string;
  sign: CryptoKeyPair;
  box: CryptoKeyPair;
}

export interface KeyStore {
  get(): Promise<StoredIdentity | null>;
  put(value: StoredIdentity): Promise<void>;
}

export function memoryKeyStore(): KeyStore {
  let value: StoredIdentity | null = null;
  return { get: async () => value, put: async (v) => void (value = v) };
}

const DB = "isymotron-link";
const STORE = "identity";
const KEY = "self";

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export function indexedDbKeyStore(factory: IDBFactory = indexedDB): KeyStore {
  const open = (): Promise<IDBDatabase> => {
    const req = factory.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    return request(req);
  };
  return {
    async get() {
      const db = await open();
      try {
        return ((await request(db.transaction(STORE, "readonly").objectStore(STORE).get(KEY))) as StoredIdentity | undefined) ?? null;
      } finally {
        db.close();
      }
    },
    async put(value) {
      const db = await open();
      try {
        await request(db.transaction(STORE, "readwrite").objectStore(STORE).put(value, KEY));
      } finally {
        db.close();
      }
    },
  };
}

/** The phone's identity: created once, then always the same one. */
export async function loadOrCreateIdentity(store: KeyStore, name = defaultName()): Promise<LinkIdentity> {
  const existing = await store.get();
  if (existing) return identityFromKeys(existing.name, existing.sign, existing.box, existing.createdAt);
  const { sign, box } = await generateKeys();
  const stored: StoredIdentity = { name, createdAt: new Date().toISOString(), sign, box };
  await store.put(stored);
  return identityFromKeys(stored.name, sign, box, stored.createdAt);
}
