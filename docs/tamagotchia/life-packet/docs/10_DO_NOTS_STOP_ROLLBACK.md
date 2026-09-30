# 10 — DO NOTS / Stop / Rollback

## DO NOTS

- No reescribir el motor para hacerlo “agentic”.
- No dar tools al GUS en V1.
- No dejar que el modelo escriba `World`.
- No guardar transcript infinito.
- No mezclar GGUF en el backup de criatura.
- No forzar el catálogo completo antes de demostrar el bridge mínimo.
- No romper la PWA.
- No declarar “funciona en iPhone/Android” si sólo pasó simulator/emulator.
- No copiar código de iSyCode Móvil sin revisar licencia/provenance/dependencias.
- No refactorizar UI, engine o store fuera de lo necesario.
- No meter PvP en el mismo PR que el runtime local.
- No introducir una base vectorial sólo porque “memoria de IA”.

## Stop conditions

Detener implementación y reportar si:

1. se descubre una divergencia estructural grande del repo;
2. el save actual no permite migración segura;
3. el bridge nativo exige permisos inesperados;
4. una dependencia arrastra red/filesystem no deseado;
5. una licencia impide distribución/uso;
6. el runtime mata la app repetidamente antes de poder registrar evidencia;
7. hay riesgo de pérdida de saves existentes.

## Rollback técnico

Feature flag conceptual:

```text
creatureMindMode =
  fallback
  remote
  local
```

Si local falla o se retira:

- `fallback` siempre existe;
- no se elimina Context Box histórico;
- no se elimina save;
- no se requiere downgrade destructivo.

## Rollback de schema

Toda migración de Context Box/save:

- versionada;
- idempotente si es posible;
- con backup anterior antes de escritura destructiva;
- con test de fixtures de versiones previas.
