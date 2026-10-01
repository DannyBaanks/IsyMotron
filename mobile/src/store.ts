/**
 * What the phone remembers besides its keys: the PCs it paired with (public data only:
 * name, public keys, address) and its own receipts. Never private keys, never task bodies
 * beyond what the human typed, never anything a PC told it that was not sealed.
 */
import type { Peer } from "./link/envelope";

export interface KeyValue {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const PEERS_KEY = "isymotron.peers.v1";
export const RECEIPTS_KEY = "isymotron.receipts.v1";
export const MAX_RECEIPTS = 200;

export interface PhoneReceipt {
  kind: "link_paired" | "link_delegated" | "link_cancelled" | "link_forgotten";
  at: string;
  office_id: string;
  name: string;
  task_id?: string;
  title?: string;
}

function read<T>(kv: KeyValue, key: string, fallback: T): T {
  try {
    const value = JSON.parse(kv.getItem(key) ?? "null");
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

export function loadPeers(kv: KeyValue): Record<string, Peer> {
  const peers = read<Record<string, Peer>>(kv, PEERS_KEY, {});
  return peers && typeof peers === "object" && !Array.isArray(peers) ? peers : {};
}

/** Pin a PC. The first paired_at wins, like the PC's trust_peer. */
export function trustPeer(kv: KeyValue, peer: Peer, now = new Date()): Peer {
  const peers = loadPeers(kv);
  const prev = peers[peer.office_id];
  const pinned: Peer = { ...peer, addresses: [...new Set([...(peer.addresses ?? []), ...(prev?.addresses ?? [])])], paired_at: prev?.paired_at ?? now.toISOString() };
  peers[peer.office_id] = pinned;
  kv.setItem(PEERS_KEY, JSON.stringify(peers));
  return pinned;
}

export function forgetPeer(kv: KeyValue, officeId: string): void {
  const peers = loadPeers(kv);
  delete peers[officeId];
  kv.setItem(PEERS_KEY, JSON.stringify(peers));
}

export function loadReceipts(kv: KeyValue): PhoneReceipt[] {
  const list = read<PhoneReceipt[]>(kv, RECEIPTS_KEY, []);
  return Array.isArray(list) ? list : [];
}

export function addReceipt(kv: KeyValue, receipt: Omit<PhoneReceipt, "at">, now = new Date()): PhoneReceipt {
  const entry: PhoneReceipt = { ...receipt, at: now.toISOString() };
  kv.setItem(RECEIPTS_KEY, JSON.stringify([...loadReceipts(kv), entry].slice(-MAX_RECEIPTS)));
  return entry;
}

export function memoryKv(): KeyValue {
  const map = new Map<string, string>();
  return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => void map.set(k, v) };
}

/** "123456" → "123 456", easier to read aloud and to compare. */
export const spacedCode = (code: string): string => `${code.slice(0, 3)} ${code.slice(3)}`;
