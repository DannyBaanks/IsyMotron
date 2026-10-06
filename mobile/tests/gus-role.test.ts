import { describe, expect, it } from 'vitest';
import { GUS_SYSTEM_PROMPT } from '../src/gus/contracts';

describe('GUS role contract', () => {
  it('gives the model a final-answer-only role with explicit capability limits', () => {
    expect(GUS_SYSTEM_PROMPT).toContain('No muestres razonamiento interno');
    expect(GUS_SYSTEM_PROMPT).toContain('Entrega solo la respuesta final');
    expect(GUS_SYSTEM_PROMPT).toContain('No tienes acceso a herramientas, Link, archivos, permisos ni a la PC enlazada');
    expect(GUS_SYSTEM_PROMPT).toContain('No afirmes haber ejecutado acciones');
  });
});
