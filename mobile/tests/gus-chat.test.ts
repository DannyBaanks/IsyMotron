import { describe, expect, it, vi } from 'vitest';
import type { GusMessage, GusProvider } from '../src/gus/contracts';
import { createGusChat } from '../src/gus/chat';
import { GUS_MODELS } from '../src/gus/catalog.generated';
import { createGusSecureStore } from '../src/gus/credentials';

function setup() {
  const localComplete = vi.fn(async (_messages: readonly GusMessage[], _signal?: AbortSignal) => 'respuesta local');
  const local: GusProvider = { complete: localComplete };
  const remote = { complete: vi.fn(async () => 'respuesta remota') } as GusProvider;
  const secureStore = createGusSecureStore({
    getRemoteConfig: vi.fn(async () => null), saveRemoteConfig: vi.fn(async () => {}),
    getApiKey: vi.fn(async () => ({ apiKey: null })), saveApiKey: vi.fn(async () => {}), clearRemoteConfig: vi.fn(async () => {}),
  });
  const models = {
    downloadModel: vi.fn(async () => {}), cancelDownload: vi.fn(async () => {}), cancel: vi.fn(async () => {}),
    importModels: vi.fn(async () => ({ cancelled: false, models: [{ id: GUS_MODELS[0]!.id, name: GUS_MODELS[0]!.name }] })),
    exportModel: vi.fn(async () => ({ cancelled: false })),
    listModels: vi.fn(async () => ({ available: true, models: [{ id: GUS_MODELS[0]!.id, name: GUS_MODELS[0]!.name, installed: true }] })),
    selectModel: vi.fn(), onProgress: vi.fn(async () => ({ remove: vi.fn() })),
  };
  const chat = createGusChat({ local, remote, secureStore, catalogue: GUS_MODELS, models });
  return { chat, local, localComplete, remote, models, secureStore };
}

describe('GUS chat controller', () => {
  it('rejects blank messages and keeps user/assistant turns only in memory', async () => {
    const { chat, localComplete } = setup();
    await chat.send('  ');
    expect(chat.getState().error).toMatch(/escribe/i);
    expect(localComplete).not.toHaveBeenCalled();
    await chat.send('hola');
    expect(chat.getState().messages.map(({ role, content }) => [role, content])).toEqual([
      ['user', 'hola'], ['assistant', 'respuesta local'],
    ]);
  });

  it('includes the fixed system message exactly once and never persists conversation text', async () => {
    const { chat, localComplete } = setup();
    await chat.send('secreto de conversación');
    const [messages] = localComplete.mock.calls[0]!;
    expect(messages.filter((message) => message.role === 'system')).toHaveLength(1);
    expect(JSON.stringify(chat.getState())).toContain('secreto de conversación');
    expect(localComplete).toHaveBeenCalledOnce();
  });

  it('preserves explicit route selection after provider failure and does not fallback', async () => {
    const { chat, local, remote } = setup();
    const failedLocal = vi.fn(async (_messages: readonly GusMessage[], _signal?: AbortSignal) => { throw new Error('local failed'); });
    local.complete = failedLocal;
    chat.selectMode('local');
    await chat.send('hola');
    expect(chat.getState().mode).toBe('local');
    expect(remote.complete).not.toHaveBeenCalled();
    expect(chat.getState().error).toContain('local failed');
  });

  it('keeps the selected mode for the current controller session', () => {
    const { chat } = setup();
    chat.selectMode('remote');
    expect(chat.getState().mode).toBe('remote');
    chat.clearSession();
    expect(chat.getState().mode).toBe('remote');
  });

  it('publishes loading state and cancellation aborts generation and calls native cancel', async () => {
    let resolve!: (value: string) => void;
    const { chat, local, models } = setup();
    local.complete = vi.fn((_messages: readonly GusMessage[], _signal?: AbortSignal) => new Promise<string>((done) => { resolve = done; }));
    const pending = chat.send('hola');
    expect(chat.getState().loading).toBe(true);
    await chat.cancel();
    expect(models.cancel).toHaveBeenCalledOnce();
    expect(chat.getState().loading).toBe(false);
    resolve('tardía');
    await pending;
    expect(chat.getState().messages.some((message) => message.content === 'tardía')).toBe(false);
  });

  it('reports model inventory and forwards download, import, and export outcomes', async () => {
    const { chat, models } = setup();
    await chat.refreshModels();
    expect(chat.getState().installedModelIds).toContain(GUS_MODELS[0]!.id);
    await chat.downloadModel(GUS_MODELS[0]!.id);
    await chat.importModels();
    expect(chat.getState().notice).toMatch(/import/i);
    await chat.exportModel(GUS_MODELS[0]!.id);
    expect(models.downloadModel).toHaveBeenCalledWith(GUS_MODELS[0]!.id);
    expect(models.importModels).toHaveBeenCalledOnce();
    expect(models.exportModel).toHaveBeenCalledWith(GUS_MODELS[0]!.id);
    expect(chat.getState().notice).toMatch(/copia/i);
  });

  it('removes prior turns and aborts in-flight output when clearing the session', async () => {
    const { chat } = setup();
    await chat.send('hola');
    chat.clearSession();
    expect(chat.getState().messages).toEqual([]);
    expect(chat.getState().loading).toBe(false);
  });
});
