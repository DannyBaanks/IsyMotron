import { describe, expect, it } from 'vitest';
import { composeDelegateFromMessages } from '../src/gus/compose';

describe('composeDelegateFromMessages', () => {
  it('returns null when there is no user message', () => {
    expect(composeDelegateFromMessages([{ role: 'assistant', content: 'hola' }])).toBeNull();
  });

  it('uses the last user message as title and body', () => {
    const out = composeDelegateFromMessages([
      { role: 'user', content: 'primero' },
      { role: 'assistant', content: 'ok' },
      { role: 'user', content: 'leéme la foto del inbox' },
    ]);
    expect(out?.title).toBe('leéme la foto del inbox');
    expect(out?.body).toContain('leéme la foto del inbox');
    expect(out?.body).toContain('respuesta GUS: ok');
  });

  it('clips the title at 60 chars', () => {
    const out = composeDelegateFromMessages([{ role: 'user', content: 'x'.repeat(200) }]);
    expect(out?.title.length).toBe(60);
  });
});
