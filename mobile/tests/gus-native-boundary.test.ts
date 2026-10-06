import { describe, expect, it, vi } from 'vitest';
import { createNativeGus } from '../src/gus/native';

describe('GUS native bridge boundary', () => {
  it('sends only a catalogue ID and bounded chat turns with fixed generation limits', async () => {
    const generate = vi.fn(async (_args: { modelId: string; messages: Array<{ role: string; content: string }>; contextTokens: number; maxTokens: number }) => ({ text: 'ok' }));
    const localBridge = {
      listModels: vi.fn(async () => ({ available: true, models: [] })),
      downloadModel: vi.fn(async () => ({ installed: true })), cancelDownload: vi.fn(async () => ({ cancelled: false })),
      importModels: vi.fn(async () => ({ cancelled: true, models: [] })),
      exportModel: vi.fn(async () => ({ cancelled: false })), generate,
      cancel: vi.fn(async () => ({ cancelled: true })), unload: vi.fn(async () => ({ cancelled: true })),
      addListener: vi.fn(async () => ({ remove: vi.fn() })),
    };
    const secrets = {
      getRemoteConfig: vi.fn(async () => null), saveRemoteConfig: vi.fn(async () => {}),
      getApiKey: vi.fn(async () => ({ apiKey: null })), saveApiKey: vi.fn(async () => {}), clearRemoteConfig: vi.fn(async () => {}),
    };
    const native = createNativeGus(localBridge, secrets, true);
    await native.local!.complete([{ role: 'user', content: 'hola' }]);
    expect(generate).toHaveBeenCalledWith({
      modelId: expect.any(String), messages: [{ role: 'user', content: 'hola' }], contextTokens: 2048, maxTokens: 160,
    });
    const payload = generate.mock.calls[0]![0] as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual(['contextTokens', 'maxTokens', 'messages', 'modelId']);
    expect(JSON.stringify(payload)).not.toMatch(/link|lease|filepath|path/i);
  });

  it('does not expose local controls outside the native runtime while leaving secure credential adapter available', () => {
    const native = createNativeGus({} as never, {} as never, false);
    expect(native.local).toBeNull();
    expect(native.models).toBeNull();
    expect(native.secureStore).toBeDefined();
  });
});
