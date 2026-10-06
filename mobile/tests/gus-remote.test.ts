import { describe, expect, it, vi } from 'vitest';
import { routeGus } from '../src/gus/routing';
import { createRemoteProvider, GusRemoteError, NVIDIA_NIM_PRESET } from '../src/gus/remote';
import { createGusSecureStore } from '../src/gus/credentials';

const config = { baseUrl: 'https://api.example.test/v1', model: 'sample-model' };
const goodResponse = () => new Response(JSON.stringify({ choices: [{ message: { content: 'hola desde nube' } }] }), { status: 200 });

describe('GUS remote provider', () => {
  it('posts only the active chat plus the shared system prompt and keeps the key in Authorization', async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => goodResponse());
    const keyProvider = vi.fn(async () => 'secret-fixture-key');
    const provider = createRemoteProvider(config, keyProvider, fetcher as typeof fetch);
    await expect(provider.complete([{ role: 'user', content: '¿Qué es GUS?' }])).resolves.toBe('hola desde nube');
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0]!;
    expect(String(url)).toBe('https://api.example.test/v1/chat/completions');
    expect(new Headers(init?.headers).get('authorization')).toBe('Bearer secret-fixture-key');
    const body = JSON.parse(String(init?.body));
    expect(body).toEqual({
      model: 'sample-model',
      max_tokens: 160,
      stream: false,
      messages: [
        { role: 'system', content: expect.any(String) },
        { role: 'user', content: '¿Qué es GUS?' },
      ],
    });
    expect(JSON.stringify(body)).not.toContain('secret-fixture-key');
    expect(keyProvider).toHaveBeenCalledOnce();
  });

  it('uses NVIDIA NIM as a quick-fill preset without hiding its explicit mode choice', () => {
    expect(NVIDIA_NIM_PRESET).toEqual({
      baseUrl: 'https://integrate.api.nvidia.com/v1',
      model: 'nvidia/nemotron-3-nano-30b-a3b',
    });
  });

  it('adapts native secure credentials without mixing the API key into remote config', async () => {
    let savedConfig: typeof config | null = null;
    let savedKey: string | null = null;
    const bridge = {
      getRemoteConfig: vi.fn(async () => savedConfig),
      saveRemoteConfig: vi.fn(async (value: typeof config) => { savedConfig = value; }),
      getApiKey: vi.fn(async () => ({ apiKey: savedKey })),
      saveApiKey: vi.fn(async ({ apiKey }: { apiKey: string }) => { savedKey = apiKey; }),
      clearRemoteConfig: vi.fn(async () => { savedConfig = null; savedKey = null; }),
    };
    const secureStore = createGusSecureStore(bridge);
    await secureStore.saveRemoteConfig({ baseUrl: 'https://api.example.test/v1/', model: ' model-id ' });
    expect(await secureStore.getRemoteConfig()).toEqual({ baseUrl: 'https://api.example.test/v1', model: 'model-id' });
    await secureStore.saveApiKey('secret-fixture-key');
    expect(await secureStore.getApiKey()).toBe('secret-fixture-key');
    expect(await secureStore.getRemoteConfig()).not.toHaveProperty('apiKey');
    await secureStore.clearRemoteConfig();
    expect(await secureStore.getRemoteConfig()).toBeNull();
    expect(await secureStore.getApiKey()).toBeNull();
  });

  it.each([
    ['plain HTTP', { ...config, baseUrl: 'http://api.example.test/v1' }],
    ['embedded credentials', { ...config, baseUrl: 'https://user:pass@api.example.test/v1' }],
    ['query string', { ...config, baseUrl: 'https://api.example.test/v1?key=leak' }],
    ['fragment', { ...config, baseUrl: 'https://api.example.test/v1#private' }],
  ])('rejects %s endpoint before sending a request', async (_label, badConfig) => {
    const fetcher = vi.fn(async () => goodResponse());
    expect(() => createRemoteProvider(badConfig, async () => 'secret-fixture-key', fetcher as typeof fetch))
      .toThrowError(GusRemoteError);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('rejects when the secure store has no key and sends no request', async () => {
    const fetcher = vi.fn(async () => goodResponse());
    const provider = createRemoteProvider(config, async () => null, fetcher as typeof fetch);
    await expect(provider.complete([{ role: 'user', content: 'hello' }])).rejects.toMatchObject({ code: 'missing_api_key' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it.each([401, 429, 500, 503])('reports HTTP %i without reading or exposing provider response bodies', async (status) => {
    const fetcher = vi.fn(async () => new Response('server body with private info', { status }));
    const provider = createRemoteProvider(config, async () => 'secret-fixture-key', fetcher as typeof fetch);
    await expect(provider.complete([{ role: 'user', content: 'hello' }])).rejects.toMatchObject({ code: 'http', status });
  });

  it('reports a queued NVIDIA request explicitly instead of silently switching providers', async () => {
    const fetcher = vi.fn(async () => new Response('{"requestId":"pending-id"}', { status: 202 }));
    const provider = createRemoteProvider(NVIDIA_NIM_PRESET, async () => 'secret-fixture-key', fetcher as typeof fetch);
    const local = { complete: vi.fn(async () => 'local') };
    await expect(routeGus('remote', { local, remote: provider }).complete([{ role: 'user', content: 'hello' }]))
      .rejects.toMatchObject({ code: 'http', status: 202 });
    expect(local.complete).not.toHaveBeenCalled();
  });

  it('reports timeout, caller cancellation, malformed JSON, and missing response content', async () => {
    vi.useFakeTimers();
    try {
      const hanging = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      }));
      const timeoutProvider = createRemoteProvider(config, async () => 'key', hanging as typeof fetch, { timeoutMs: 100 });
      const timeout = timeoutProvider.complete([{ role: 'user', content: 'hello' }]);
      const timeoutAssertion = expect(timeout).rejects.toMatchObject({ code: 'timeout' });
      await vi.advanceTimersByTimeAsync(101);
      await timeoutAssertion;
    } finally { vi.useRealTimers(); }

    const fetcher = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
    }));
    const provider = createRemoteProvider(config, async () => 'key', fetcher as typeof fetch);
    const controller = new AbortController();
    const cancelled = provider.complete([{ role: 'user', content: 'hello' }], controller.signal);
    controller.abort();
    await expect(cancelled).rejects.toMatchObject({ code: 'aborted' });

    const malformed = createRemoteProvider(config, async () => 'key', vi.fn(async () => new Response('{')) as typeof fetch);
    await expect(malformed.complete([{ role: 'user', content: 'hello' }])).rejects.toBeInstanceOf(GusRemoteError);
    const noContent = createRemoteProvider(config, async () => 'key', vi.fn(async () => new Response('{"choices":[]}')) as typeof fetch);
    await expect(noContent.complete([{ role: 'user', content: 'hello' }])).rejects.toMatchObject({ code: 'invalid_response' });
  });
});
