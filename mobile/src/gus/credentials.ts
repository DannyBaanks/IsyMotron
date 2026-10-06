export type GusRemoteConfig = {
  baseUrl: string;
  model: string;
};

export interface GusSecureStore {
  getRemoteConfig(): Promise<GusRemoteConfig | null>;
  saveRemoteConfig(config: GusRemoteConfig): Promise<void>;
  getApiKey(): Promise<string | null>;
  saveApiKey(apiKey: string): Promise<void>;
  clearRemoteConfig(): Promise<void>;
}

/** Shape exposed by the native Keychain / Android Keystore plugins. */
export interface GusSecretsBridge {
  getRemoteConfig(): Promise<GusRemoteConfig | null | undefined>;
  saveRemoteConfig(config: GusRemoteConfig): Promise<void>;
  getApiKey(): Promise<{ apiKey?: string | null } | null | undefined>;
  saveApiKey(options: { apiKey: string }): Promise<void>;
  clearRemoteConfig(): Promise<void>;
}

export function validateGusRemoteConfig(value: GusRemoteConfig): GusRemoteConfig {
  let url: URL;
  try { url = new URL(value.baseUrl); }
  catch { throw new TypeError('Remote GUS endpoint must be a valid HTTPS URL.'); }
  if (url.protocol !== 'https:' || !url.hostname || url.username || url.password || url.search || url.hash) {
    throw new TypeError('Remote GUS endpoint must use HTTPS and must not contain credentials, a query, or a fragment.');
  }
  const model = value.model.trim();
  if (!model || model.length > 256) throw new TypeError('Remote GUS model name is empty or too long.');
  return { baseUrl: url.toString().replace(/\/+$/, ''), model };
}

export function createGusSecureStore(bridge: GusSecretsBridge): GusSecureStore {
  return {
    async getRemoteConfig() {
      const value = await bridge.getRemoteConfig();
      return value ? validateGusRemoteConfig(value) : null;
    },
    async saveRemoteConfig(config) { await bridge.saveRemoteConfig(validateGusRemoteConfig(config)); },
    async getApiKey() {
      const result = await bridge.getApiKey();
      return result?.apiKey ?? null;
    },
    async saveApiKey(apiKey) {
      if (!apiKey.trim() || apiKey.length > 4096) throw new TypeError('Remote GUS API key is empty or too long.');
      await bridge.saveApiKey({ apiKey });
    },
    async clearRemoteConfig() { await bridge.clearRemoteConfig(); },
  };
}
