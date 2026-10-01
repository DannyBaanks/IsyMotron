import type { GusMode, GusProvider, GusRouteProviders } from './contracts';

export class GusUnavailableError extends Error {
  constructor(readonly mode: GusMode) {
    super(mode === 'local' ? 'El runtime local de GUS no está disponible.' : 'Configura un proveedor remoto para usar GUS remoto.');
    this.name = 'GusUnavailableError';
  }
}

export function routeGus(mode: GusMode, providers: GusRouteProviders): GusProvider {
  const provider = providers[mode];
  if (!provider) throw new GusUnavailableError(mode);
  return provider;
}
