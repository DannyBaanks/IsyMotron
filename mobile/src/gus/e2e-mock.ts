import type { GusMessage, GusProvider } from './contracts';
import type { GusProgress } from './native';
import { GUS_MODELS } from './catalog.generated';
import type { GusAppDeps, GusModelActions } from './chat';
import type { GusRemoteConfig, GusSecureStore } from './credentials';

// Deliberate leak sentinel. The production build check rejects this marker anywhere in dist.
export const GUS_E2E_MOCK_SENTINEL = 'ISYMOTRON_GUS_E2E_ONLY_DO_NOT_SHIP_4F31';

const installed = new Set<string>();
const listeners = new Set<(progress: GusProgress) => void>();
let remoteConfig: GusRemoteConfig | null = null;
let apiKey: string | null = null;

const local: GusProvider = {
  async complete(messages: readonly GusMessage[], signal?: AbortSignal) {
    if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    const user = messages.filter((message) => message.role === 'user').at(-1)?.content ?? '';
    if (user.includes('fallo local')) throw new Error('runtime local falló de forma simulada');
    return `Respuesta local simulada: ${user}`;
  },
};

const models: GusModelActions = {
  async listModels() { return { available: true, models: GUS_MODELS.map(({ id, name }) => ({ id, name, installed: installed.has(id) })) }; },
  async downloadModel(id) {
    const model = GUS_MODELS.find((candidate) => candidate.id === id);
    if (!model) throw new Error('Modelo fuera del catálogo.');
    for (const listener of listeners) listener({ modelId: id, receivedBytes: model.byteCount, totalBytes: model.byteCount });
    installed.add(id);
    return { installed: true };
  },
  async cancelDownload(id) { return { cancelled: installed.delete(id) }; },
  async importModels() { const model = GUS_MODELS[0]!; installed.add(model.id); return { cancelled: false, models: [{ id: model.id, name: model.name }] }; },
  async exportModel(id) { return { cancelled: !installed.has(id) }; },
  selectModel(id) { if (!GUS_MODELS.some((model) => model.id === id)) throw new Error('Modelo fuera del catálogo.'); },
  async cancel() { return { cancelled: true }; },
  async onProgress(listener) { listeners.add(listener); return { remove: () => listeners.delete(listener) }; },
};

const secureStore: GusSecureStore = {
  async getRemoteConfig() { return remoteConfig; },
  async saveRemoteConfig(config) { remoteConfig = { ...config }; },
  async getApiKey() { return apiKey; },
  async saveApiKey(value) { apiKey = value; },
  async clearRemoteConfig() { remoteConfig = null; apiKey = null; },
};

export const e2eMockGus: GusAppDeps = { local, remote: null, secureStore, catalogue: GUS_MODELS, models };
