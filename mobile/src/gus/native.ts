import { Capacitor, registerPlugin } from '@capacitor/core';
import type { GusMessage, GusProvider } from './contracts';
import { GUS_MODELS, getGusModel, type GusModelManifest } from './catalog.generated';
import { createGusSecureStore, type GusRemoteConfig, type GusSecretsBridge, type GusSecureStore } from './credentials';

export type GusProgress = { modelId: string; receivedBytes: number; totalBytes: number };
export type GusLocalModel = Pick<GusModelManifest, 'id' | 'name'> & { installed: boolean };
export interface GusLocalBridge {
  listModels(): Promise<{ available: boolean; models: GusLocalModel[] }>;
  downloadModel(options: { modelId: string }): Promise<{ installed: boolean }>;
  cancelDownload(options: { modelId: string }): Promise<{ cancelled: boolean }>;
  importModels(): Promise<{ cancelled: boolean; models: Array<{ id: string; name: string }> }>;
  exportModel(options: { modelId: string }): Promise<{ cancelled: boolean }>;
  generate(options: { modelId: string; messages: GusMessage[]; contextTokens: number; maxTokens: number }): Promise<{ text: string }>;
  cancel(): Promise<{ cancelled?: boolean }>;
  unload(): Promise<{ cancelled?: boolean }>;
  addListener(event: 'downloadProgress', listener: (progress: GusProgress) => void): Promise<{ remove(): void }>;
}

const localPlugin = registerPlugin<GusLocalBridge>('GusLocal');
const secretsPlugin = registerPlugin<GusSecretsBridge>('GusSecrets');

export function isNativeGusAvailable(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('GusLocal') && Capacitor.isPluginAvailable('GusSecrets');
}

const unavailableSecureStore: GusSecureStore = {
  async getRemoteConfig() { return null; }, async getApiKey() { return null; },
  async saveRemoteConfig(_value: GusRemoteConfig) { throw new Error('El guardado seguro remoto solo está disponible en la app nativa.'); },
  async saveApiKey(_apiKey: string) { throw new Error('La llave remota no se puede guardar de forma segura en el navegador.'); },
  async clearRemoteConfig() { throw new Error('El guardado seguro remoto solo está disponible en la app nativa.'); },
};

export function createNativeGus(local: GusLocalBridge, secrets: GusSecretsBridge, available: boolean) {
  let selectedModelId = GUS_MODELS[0]?.id ?? '';
  const models = available ? {
    listModels: () => local.listModels(),
    downloadModel(id: string) { requireCatalogueModel(id); return local.downloadModel({ modelId: id }); },
    cancelDownload(id: string) { requireCatalogueModel(id); return local.cancelDownload({ modelId: id }); },
    importModels: () => local.importModels(),
    exportModel(id: string) { requireCatalogueModel(id); return local.exportModel({ modelId: id }); },
    selectModel(id: string) { requireCatalogueModel(id); selectedModelId = id; },
    cancel: () => local.cancel(),
    onProgress(listener: (progress: GusProgress) => void) { return local.addListener('downloadProgress', listener); },
  } : null;
  const provider: GusProvider | null = available ? {
    async complete(messages, signal) {
      if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
      const result = await local.generate({ modelId: selectedModelId, messages: messages.map(({ role, content }) => ({ role, content })), contextTokens: 2048, maxTokens: 160 });
      if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
      return result.text;
    },
  } : null;
  const secureStore = available ? createGusSecureStore(secrets) : unavailableSecureStore;
  return { local: provider, models, secureStore, available };
}

function requireCatalogueModel(id: string): void {
  if (!getGusModel(id)) throw new TypeError('Modelo GUS no reconocido.');
}

export const nativeGus = createNativeGus(localPlugin, secretsPlugin, isNativeGusAvailable());
