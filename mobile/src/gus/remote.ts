import { GUS_SYSTEM_PROMPT, type GusMessage, type GusProvider } from './contracts';
import { validateGusRemoteConfig, type GusRemoteConfig } from './credentials';

export const NVIDIA_NIM_PRESET: Readonly<GusRemoteConfig> = Object.freeze({
  baseUrl: 'https://integrate.api.nvidia.com/v1',
  model: 'nvidia/nemotron-3-nano-30b-a3b',
});

export type GusRemoteErrorCode = 'invalid_config' | 'missing_api_key' | 'http' | 'timeout' | 'aborted' | 'invalid_response';

export class GusRemoteError extends Error {
  constructor(public readonly code: GusRemoteErrorCode, message: string, public readonly status?: number) {
    super(message);
    this.name = 'GusRemoteError';
  }
}

export type GusFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type GusRemoteOptions = { timeoutMs?: number };

const DEFAULT_TIMEOUT_MS = 90_000;
const MAX_MESSAGES = 64;
const MAX_CONVERSATION_CHARACTERS = 32_000;

export function createRemoteProvider(
  config: GusRemoteConfig,
  getApiKey: () => Promise<string | null>,
  fetcher: GusFetch = fetch,
  options: GusRemoteOptions = {},
): GusProvider {
  let validated: GusRemoteConfig;
  try { validated = validateGusRemoteConfig(config); }
  catch (error) { throw new GusRemoteError('invalid_config', error instanceof Error ? error.message : 'Invalid remote GUS configuration.'); }
  const endpoint = new URL(`${validated.baseUrl}/chat/completions`);
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 10 * 60_000) {
    throw new GusRemoteError('invalid_config', 'Remote GUS timeout must be between 1 ms and 10 minutes.');
  }

  return {
    async complete(messages: readonly GusMessage[], externalSignal?: AbortSignal): Promise<string> {
      if (externalSignal?.aborted) throw new GusRemoteError('aborted', 'Remote GUS request was cancelled.');
      if (messages.length === 0 || messages.length > MAX_MESSAGES || messages.some((message) =>
        !['user', 'assistant', 'system'].includes(message.role) || typeof message.content !== 'string' || message.content.length > 12_000)) {
        throw new GusRemoteError('invalid_response', 'Remote GUS conversation is empty or exceeds the message limits.');
      }
      const conversationCharacters = messages.reduce((total, message) => total + message.content.length, 0);
      if (conversationCharacters > MAX_CONVERSATION_CHARACTERS) throw new GusRemoteError('invalid_response', 'Remote GUS conversation is too long.');
      const apiKey = await getApiKey();
      if (!apiKey?.trim()) throw new GusRemoteError('missing_api_key', 'Save an API key in GUS settings before selecting remote mode.');
      if (externalSignal?.aborted) throw new GusRemoteError('aborted', 'Remote GUS request was cancelled.');

      const controller = new AbortController();
      let timedOut = false;
      const abortFromCaller = () => controller.abort(externalSignal?.reason);
      externalSignal?.addEventListener('abort', abortFromCaller, { once: true });
      const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
      const activeMessages = messages.filter((message) => message.role !== 'system');
      const body = {
        model: validated.model,
        max_tokens: 160,
        stream: false,
        messages: [{ role: 'system', content: GUS_SYSTEM_PROMPT }, ...activeMessages],
      };

      try {
        const response = await fetcher(endpoint, {
          method: 'POST',
          headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        if (response.status === 202 || !response.ok) throw new GusRemoteError('http', `Remote GUS returned HTTP ${response.status}.`, response.status);
        let payload: unknown;
        try { payload = await response.json(); }
        catch { throw new GusRemoteError('invalid_response', 'Remote GUS returned malformed JSON.'); }
        const content = (payload as { choices?: { message?: { content?: unknown } }[] } | null)?.choices?.[0]?.message?.content;
        if (typeof content !== 'string' || !content.trim()) throw new GusRemoteError('invalid_response', 'Remote GUS response did not contain assistant text.');
        return content;
      } catch (error) {
        if (error instanceof GusRemoteError) throw error;
        if (timedOut) throw new GusRemoteError('timeout', 'Remote GUS request timed out.');
        if (externalSignal?.aborted) throw new GusRemoteError('aborted', 'Remote GUS request was cancelled.');
        throw new GusRemoteError('http', 'Remote GUS could not reach the selected HTTPS provider.');
      } finally {
        clearTimeout(timeout);
        externalSignal?.removeEventListener('abort', abortFromCaller);
      }
    },
  };
}
