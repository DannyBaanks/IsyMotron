import type { GusMessage, GusMode } from './contracts';
import type { GusModelManifest } from './catalog.generated';

export type GusChatState = {
  mode: GusMode;
  messages: GusMessage[];
  loading: boolean;
  error: string;
  notice: string;
  progress: { modelId: string; receivedBytes: number; totalBytes: number } | null;
  installedModelIds: string[];
  selectedModelId: string;
};

export function initialGusChatState(catalogue: readonly GusModelManifest[]): GusChatState {
  return { mode: 'local', messages: [], loading: false, error: '', notice: '', progress: null, installedModelIds: [], selectedModelId: catalogue[0]?.id ?? '' };
}
