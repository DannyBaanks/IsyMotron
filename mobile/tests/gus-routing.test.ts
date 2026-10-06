import { describe, expect, it, vi } from 'vitest';
import { GUS_SYSTEM_PROMPT, type GusProvider } from '../src/gus/contracts';
import { GusUnavailableError, routeGus } from '../src/gus/routing';

const provider = (): GusProvider => ({ complete: vi.fn(async () => 'respuesta') });

describe('routeGus', () => {
  it('selects the local provider when local mode is selected', () => {
    const local = provider();
    expect(routeGus('local', { local, remote: provider() })).toBe(local);
  });

  it('selects the remote provider only when remote mode is selected', () => {
    const remote = provider();
    expect(routeGus('remote', { local: provider(), remote })).toBe(remote);
  });

  it('reports a typed unavailable error when local runtime is missing', () => {
    expect(() => routeGus('local', { local: null, remote: provider() })).toThrow(GusUnavailableError);
  });

  it('reports a typed unavailable error when remote configuration is missing', () => {
    expect(() => routeGus('remote', { local: provider(), remote: null })).toThrow(GusUnavailableError);
  });

  it('propagates a local failure without calling the remote provider', async () => {
    const failure = new Error('modelo no disponible');
    const local = { complete: vi.fn(async () => { throw failure; }) };
    const remote = provider();
    await expect(routeGus('local', { local, remote }).complete([])).rejects.toBe(failure);
    expect(remote.complete).not.toHaveBeenCalled();
  });

  it('exports the advisory-only role with explicit capability and reasoning limits', () => {
    expect(GUS_SYSTEM_PROMPT).toContain('Eres GUS');
    expect(GUS_SYSTEM_PROMPT).toContain('Solo das orientación');
    expect(GUS_SYSTEM_PROMPT).toContain('No tienes acceso a herramientas, Link, archivos, permisos ni a la PC enlazada');
    expect(GUS_SYSTEM_PROMPT).toContain('No afirmes haber ejecutado acciones');
    expect(GUS_SYSTEM_PROMPT).toContain('No muestres razonamiento interno');
  });
});
