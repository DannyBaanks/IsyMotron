# Repo snapshot usado para este paquete

## TamagotchIA

- Repo: `DannyBaanks/TamagotchIA`
- `main` observado: `b7fe4b13383d50b1d857ae0574eb110c983157a4`
- `package.json`: Vite/TypeScript/Vitest + Capacitor Android/iOS/App/Local Notifications.
- `src/engine/`: commands, derived, forecast, memory, random, rules, simulation, types, world.
- `src/persona/`: contract, fallback, providers.
- `src/store/`: existe y debe inspeccionarse antes de diseñar migración.

## iSyCodeMovil

- `main` inspeccionado alrededor de `30097a5ffcdb33a18eb951590cb1ea7ec692e8d0` como base observada al momento del paquete.
- Runtime GUS visible en `Sources/Model/` para iOS y en `android/.../gus/` para Android.
- Existen catálogo, device budget, benchmark y crash forensics.

## Nota sobre “Don Zelaya fix”

Al momento de preparar el paquete, el trabajo de sampling/anti-loop estaba en PR #6 de iSyCodeMovil y no se debe asumir mergeado. Si ya fue mergeado cuando se implemente TamagotchIA, inspeccionar la versión vigente y reutilizar el comportamiento actual, no el snapshot del paquete.
