# 02 — Roadmap GUS + Context Box

## M0 — Reconocimiento y baseline

- Inspeccionar repo actual.
- Ejecutar `npm test`, `npm run check`, `npm run build` o comandos actuales equivalentes.
- Verificar builds Capacitor iOS/Android disponibles.
- Inventariar formato real de save y versión.
- Inventariar contrato actual de persona.
- Inspeccionar runtime GUS actual de iSyCode Móvil.

**Salida:** `BASELINE.md` con paths reales, versiones, tests y riesgos.

## M1 — Context Box V1 puro, sin modelo local

Construir un `ContextBoxV1` desde el `World` existente.

Primero sólo usarlo con el provider actual/fallback para demostrar que:

- el box es determinista salvo campos temporales explícitos;
- cabe dentro de un presupuesto de contexto;
- no muta estado;
- puede renderizarse en debug.

**Done:** snapshot tests + schema versionado.

## M2 — Historial y memoria por capas

Agregar persistencia para:

- tendencias de stats;
- resumen de eventos recientes;
- memorias episódicas significativas;
- relación;
- hábitos/preferencias;
- resumen conversacional;
- open threads.

No guardar transcript infinito. Ver política de memoria.

**Done:** 7 días simulados no hacen crecer el save sin límite.

## M3 — GUS sandbox contract

Crear una interfaz única, por ejemplo:

```ts
interface CreatureMind {
  generate(input: ContextBoxV1, trigger: MindTrigger): Promise<MindReply>
}
```

Implementaciones iniciales:

- deterministic fallback;
- remote provider existente;
- local native bridge placeholder.

La respuesta se valida antes de llegar a UI/memoria.

**Done:** fuzz/invalid-output tests demuestran fail-closed.

## M4 — iOS local GUS

- Reusar/adaptar llama.cpp/runtime desde iSyCode Móvil.
- Mantener modelo binario fuera del save.
- Añadir selección/import/download según el diseño actual de TamagotchIA.
- Pasar Context Box al bridge nativo.
- Recuperar respuesta estructurada.
- Integrar sampling estable para chat.
- Añadir crash/abnormal termination breadcrumbs mínimos.

**Done:** device test físico con modo avión.

## M5 — Android local GUS

- Reusar/adaptar JNI/C++/Kotlin del GUS móvil.
- Mantener mismo contrato semántico que iOS.
- No exigir identidad de implementación si Android necesita wrapper distinto.

**Done:** device test físico con modo avión.

## M6 — Continuidad real

Pruebas:

- reabrir tras 1 h, 8 h, 24 h, 72 h;
- criatura enferma y recuperada;
- cambio de comida favorita;
- evolución;
- conversación que crea open thread;
- cambio de modelo GUS;
- export/import de save.

**Done:** la mascota mantiene continuidad aunque cambie el modelo.

## M7 — UX de “mi GUS”

Añadir controles simples:

- GUS local on/off;
- modelo elegido;
- estado `cargando / listo / no cabe / falló`;
- tamaño y evidencia de compatibilidad si se reutiliza el catálogo;
- borrar modelo sin borrar la criatura;
- exportar contexto de la criatura separado del GGUF;
- vista debug del Context Box sólo en modo dev.

No convertir el juego en un dashboard de IA.

## M8 — Preparación para combate futuro

Sin implementar PvP todavía:

- versionar `CreatureProfile` exportable;
- versionar stats de combate derivados;
- crear `BattleIntent` como salida no autoritativa del GUS;
- reservar `battle_history` en memoria;
- definir receipt/replay determinista.

**Done:** el futuro PvP puede añadirse sin darle autoridad al modelo.

## M9 — Hardening y release

- backward compatibility;
- save corruption tests;
- context budget tests;
- local model crash recovery;
- thermal/memory UX;
- docs de privacidad;
- release notes;
- evidence matrix.
