export type GusMessage = {
  role: 'system' | 'user' | 'assistant';
  content: string;
};

export interface GusProvider {
  complete(messages: readonly GusMessage[], signal?: AbortSignal): Promise<string>;
}

export const GUS_SYSTEM_PROMPT =
  'Eres GUS, asistente de IsyMotron. Responde en el idioma del usuario, de forma breve y clara. Solo das orientación: no tienes acceso a herramientas, Link, archivos, permisos ni a la PC enlazada. No afirmes haber ejecutado acciones. Si no sabes un dato, dilo.';

export type GusMode = 'local' | 'remote';

export type GusRouteProviders = {
  local: GusProvider | null;
  remote: GusProvider | null;
};
