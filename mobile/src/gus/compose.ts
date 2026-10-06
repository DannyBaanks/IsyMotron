import type { GusMessage } from './contracts';

/**
 * Turns the visible GUS conversation into a Link task payload without
 * granting GUS any new authority: the human still confirms by tapping the
 * button, and the PC decides what to do with the task.
 */
export function composeDelegateFromMessages(messages: readonly GusMessage[]): { title: string; body: string } | null {
  const lastUser = [...messages].reverse().find((m) => m.role === 'user');
  if (!lastUser || !lastUser.content.trim()) return null;
  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
  return {
    title: lastUser.content.trim().slice(0, 60),
    body: lastAssistant
      ? `${lastUser.content.trim()}\n\n(respuesta GUS: ${lastAssistant.content.trim()})`
      : lastUser.content.trim(),
  };
}
