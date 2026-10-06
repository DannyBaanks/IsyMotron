import type { GusMessage, GusMode, GusProvider } from './contracts';
import { GUS_SYSTEM_PROMPT } from './contracts';
import { initialGusChatState, type GusChatState } from './chat.testable';
import type { GusModelManifest } from './catalog.generated';
import { createRemoteProvider } from './remote';
import type { GusRemoteConfig, GusSecureStore } from './credentials';
import type { GusProgress, GusLocalModel } from './native';

export interface GusModelActions {
  listModels(): Promise<{ available: boolean; models: GusLocalModel[] }>;
  downloadModel(id: string): Promise<unknown>;
  cancelDownload(id: string): Promise<unknown>;
  importModels(): Promise<{ cancelled: boolean; models: Array<{ id: string; name: string }> }>;
  exportModel(id: string): Promise<{ cancelled: boolean }>;
  selectModel(id: string): void;
  cancel(): Promise<unknown>;
  onProgress(listener: (progress: GusProgress) => void): Promise<{ remove(): void }>;
}

export type GusAppDeps = {
  local: GusProvider | null;
  remote?: GusProvider | null;
  remoteConfig?: GusRemoteConfig | null;
  secureStore: GusSecureStore;
  catalogue: readonly GusModelManifest[];
  models: GusModelActions | null;
};

export interface GusChatController {
  getState(): GusChatState;
  subscribe(listener: (state: GusChatState) => void): () => void;
  send(text: string): Promise<void>;
  cancel(): Promise<void>;
  selectMode(mode: GusMode): void;
  selectModel(id: string): void;
  downloadModel(id: string): Promise<void>;
  cancelDownload(id: string): Promise<void>;
  importModels(): Promise<void>;
  exportModel(id: string): Promise<void>;
  refreshModels(): Promise<void>;
  saveRemoteConfig(config: GusRemoteConfig): Promise<void>;
  saveApiKey(key: string): Promise<void>;
  clearSession(): void;
}

export function createGusChat(deps: GusAppDeps): GusChatController {
  let state = initialGusChatState(deps.catalogue);
  let active: AbortController | null = null;
  const listeners = new Set<(state: GusChatState) => void>();
  const publish = (patch: Partial<GusChatState>) => { state = { ...state, ...patch }; for (const listener of listeners) listener(state); };

  const controller: GusChatController = {
    getState: () => state,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    selectMode(mode) { publish({ mode, error: '', notice: '' }); },
    selectModel(id) {
      if (!deps.catalogue.some((model) => model.id === id)) { publish({ error: 'Ese modelo no está en el catálogo verificado.' }); return; }
      deps.models?.selectModel(id); publish({ selectedModelId: id, error: '', notice: '' });
    },
    async send(text) {
      const content = text.trim();
      if (!content) { publish({ error: 'Escribe un mensaje para GUS.' }); return; }
      if (state.loading) return;
      const request = new AbortController(); active = request;
      const user: GusMessage = { role: 'user', content };
      const prior = [...state.messages]; publish({ messages: [...prior, user], loading: true, error: '', notice: '' });
      try {
        let provider = state.mode === 'local' ? deps.local : deps.remote ?? null;
        if (state.mode === 'remote' && !provider) {
          const config = deps.remoteConfig ?? await deps.secureStore.getRemoteConfig();
          if (!config) throw new Error('Configura una URL HTTPS y el modelo del proveedor remoto.');
          provider = createRemoteProvider(config, () => deps.secureStore.getApiKey());
        }
        if (!provider) throw new Error(state.mode === 'local' ? 'El runtime local no está disponible en el navegador; instala la app nativa.' : 'Proveedor remoto no disponible.');
        const turns: GusMessage[] = [{ role: 'system', content: GUS_SYSTEM_PROMPT }, ...prior, user];
        const answer = await provider.complete(turns, request.signal);
        if (active === request && !request.signal.aborted) publish({ messages: [...prior, user, { role: 'assistant', content: answer }] });
      } catch (error) {
        if (!request.signal.aborted) publish({ error: error instanceof Error ? error.message : String(error) });
      } finally {
        if (active === request) { active = null; publish({ loading: false }); }
      }
    },
    async cancel() {
      const request = active; active = null; request?.abort();
      try { await deps.models?.cancel(); } catch { /* Cancellation is best-effort; the request remains aborted. */ }
      publish({ loading: false, notice: 'Generación cancelada.' });
    },
    async refreshModels() {
      if (!deps.models) return;
      try {
        const result = await deps.models.listModels();
        const installedModelIds = result.available ? result.models.filter((model) => model.installed).map((model) => model.id) : [];
        const selectedModelId = installedModelIds.includes(state.selectedModelId) ? state.selectedModelId : installedModelIds[0] ?? state.selectedModelId;
        if (installedModelIds.includes(selectedModelId) && selectedModelId !== state.selectedModelId) deps.models?.selectModel(selectedModelId);
        publish({ installedModelIds, selectedModelId });
      } catch (error) { publish({ error: error instanceof Error ? error.message : String(error) }); }
    },
    async downloadModel(id) {
      try { publish({ error: '', notice: 'Descargando y verificando el modelo…', progress: { modelId: id, receivedBytes: 0, totalBytes: 0 } }); await deps.models?.downloadModel(id); await this.refreshModels(); publish({ progress: null, notice: 'Modelo verificado e instalado.' }); }
      catch (error) { publish({ progress: null, error: error instanceof Error ? error.message : String(error) }); }
    },
    async cancelDownload(id) { try { await deps.models?.cancelDownload(id); publish({ progress: null, notice: 'Descarga cancelada; el modelo anterior se conserva.' }); } catch (error) { publish({ error: error instanceof Error ? error.message : String(error) }); } },
    async importModels() {
      try { const result = await deps.models?.importModels(); if (!result) return; await this.refreshModels(); publish({ notice: result.cancelled ? 'Importación cancelada; tus modelos no cambiaron.' : `Importación completada: ${result.models.length} modelo(s).`, error: '' }); }
      catch (error) { publish({ error: error instanceof Error ? error.message : String(error), notice: '' }); }
    },
    async exportModel(id) {
      try { const result = await deps.models?.exportModel(id); if (result) publish({ notice: result.cancelled ? 'Guardado cancelado; el modelo sigue instalado.' : 'Copia del modelo guardada.', error: '' }); }
      catch (error) { publish({ error: error instanceof Error ? error.message : String(error), notice: '' }); }
    },
    async saveRemoteConfig(config) { try { await deps.secureStore.saveRemoteConfig(config); publish({ notice: 'Proveedor remoto guardado de forma segura.', error: '' }); } catch (error) { publish({ error: error instanceof Error ? error.message : String(error) }); } },
    async saveApiKey(key) { try { await deps.secureStore.saveApiKey(key); publish({ notice: 'API key guardada en almacenamiento seguro.', error: '' }); } catch (error) { publish({ error: error instanceof Error ? error.message : String(error) }); } },
    clearSession() {
      const request = active; active = null; request?.abort();
      if (request) void deps.models?.cancel().catch(() => {});
      publish({ messages: [], loading: false, error: '', notice: 'Conversación borrada de esta sesión.' });
    },
  };
  void deps.models?.onProgress((progress) => publish({ progress })).catch(() => {});
  return controller;
}
