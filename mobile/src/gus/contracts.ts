import gusRole from './ROL.md?raw';

export type GusMessage = {
  role: 'system' | 'user' | 'assistant';
  content: string;
};

export interface GusProvider {
  complete(messages: readonly GusMessage[], signal?: AbortSignal): Promise<string>;
}

export const GUS_SYSTEM_PROMPT = gusRole.trim();

export type GusMode = 'local' | 'remote';

export type GusRouteProviders = {
  local: GusProvider | null;
  remote: GusProvider | null;
};
