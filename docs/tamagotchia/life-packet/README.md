# TamagotchIA — GUS Life Packet

Paquete de handoff para convertir la voz opcional de TamagotchIA en un **GUS local persistente**, con sandbox, memoria de contexto y continuidad de personalidad, sin cederle autoridad sobre el juego.

## Objetivo corto

La criatura debe poder tener un cerebro local que:

- recuerde su historia sin cargar conversaciones infinitas;
- conozca su estado actual y tendencias recientes de stats;
- recuerde episodios importantes, hábitos, gustos, relación con la persona y asuntos pendientes;
- responda como la criatura, no como asistente;
- funcione offline en iOS/Android cuando haya modelo local compatible;
- pueda sobrevivir reinstalaciones mediante backup del contexto;
- **no pueda modificar por sí sola stats, inventario, evolución, timestamps, combates ni archivos externos**.

La idea central es simple:

```text
motor del juego = verdad
GUS = voz + memoria + criterio de personalidad
Context Box = lo que GUS sabe en este momento
Sandbox = frontera que impide que GUS se vuelva autoridad
```

## Empieza aquí

1. `docs/00_CURRENT_BASELINE.md`
2. `docs/01_COMPOSE_MASTER.md`
3. `docs/02_ROADMAP.md`
4. `docs/03_ARCHITECTURE.md`
5. `docs/04_CONTEXT_BOX_SPEC.md`
6. `docs/05_GUS_SANDBOX_SPEC.md`
7. `docs/06_MEMORY_AND_HISTORY_POLICY.md`
8. `docs/07_CROSS_PLATFORM_INTEGRATION.md`
9. `docs/08_PVP_FUTURE_CONTRACT.md`
10. `docs/09_TEST_MATRIX.md`
11. `docs/10_DO_NOTS_STOP_ROLLBACK.md`
12. `docs/11_AGENT_HANDOFF.md`

`schemas/` y `templates/` contienen artefactos de implementación listos para adaptar después de inspeccionar el repo.

## Regla principal

**No reemplazar el motor determinista existente por un LLM.** El GUS debe vivir *encima* del juego, no gobernarlo.

## Estado de este paquete

Diseño/roadmap. No modifica el repositorio. Está basado en la inspección de `DannyBaanks/TamagotchIA` y `DannyBaanks/iSyCodeMovil` realizada el 2026-09-30. Los paths reales deben volver a inspeccionarse antes de editar porque ambos repos siguen moviéndose rápido.
