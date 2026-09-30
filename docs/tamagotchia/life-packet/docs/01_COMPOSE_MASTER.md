# 01 — Compose Master: GUS vive dentro de TamagotchIA

## Rol

Actúa como implementador principal de TamagotchIA. Trabaja sobre el repo real y verifica antes de editar. No inventes paths, APIs, capacidades ni estado de ramas.

## Objetivo

Integrar un **GUS local persistente** en TamagotchIA para iOS y Android, manteniendo la PWA funcional, de forma que cada criatura pueda tener un modelo local como voz/persona con continuidad histórica. Añadir un **Context Box** acotado y versionado que entregue al GUS la historia relevante de la criatura: estado actual, tendencias de stats, eventos recientes, memorias episódicas, hábitos/preferencias, relación, resumen conversacional y asuntos pendientes.

El motor del juego sigue siendo la única autoridad sobre stats, evolución, inventario, timestamps y reglas.

## Inspección obligatoria antes de editar

1. Inspecciona `DannyBaanks/TamagotchIA` actual.
2. Localiza el motor, persona, persistencia, UI, Capacitor iOS y Android.
3. Ejecuta tests/build actuales antes de modificar.
4. Inspecciona `DannyBaanks/iSyCodeMovil` actual y localiza el runtime GUS local vigente en iOS y Android.
5. Decide qué código puede compartirse, qué debe adaptarse y qué no debe copiarse.
6. Revisa licencias/provenance de llama.cpp y modelos antes de mover código o artefactos.
7. Si el repo cambió respecto al paquete, actualiza el plan; no fuerces los paths de este documento.

## Claim a demostrar

> Una criatura de TamagotchIA puede usar un modelo local GUS en iOS/Android, conservar continuidad de personalidad mediante un Context Box persistente y responder offline sin tener autoridad para mutar la realidad del juego.

## Falsificación

El claim NO se considera demostrado si ocurre cualquiera de estos casos:

- GUS puede mutar stats o comandos del motor sin validación de código.
- La continuidad depende de mantener todo el transcript en contexto.
- El juego deja de funcionar sin modelo local.
- El guardado del GUS rompe compatibilidad con saves previos.
- iOS o Android sólo funcionan mediante mock/simulador y se declaran como reales.
- El modelo puede acceder a filesystem/red/herramientas fuera del sandbox previsto.
- Al cambiar de modelo la criatura “olvida quién es” porque identidad y memoria estaban dentro del modelo y no en el save.

## Workload boundary

### Sí entra

- Context Box V1.
- Persistencia/migración de contexto.
- Adapter local GUS para iOS.
- Adapter local GUS para Android.
- Degradación limpia en PWA.
- Selección de modelo local compatible.
- Modelo/persona aislado del motor.
- Backup/restore del contexto.
- Tests de continuidad, seguridad y migración.
- Flight recorder mínimo para inferencia local si se reutiliza del runtime GUS.

### No entra en este primer trabajo

- PvP real por internet.
- Matchmaking.
- Ranking global.
- Economía online.
- Herramientas del sistema para GUS.
- Escritura arbitraria de archivos.
- “agente general” dentro de la mascota.
- Don Cándidos/helpers celulares.
- Rehacer todo el UI.
- Refactors generales no necesarios.

## Principio de arquitectura

```text
acción / tick / evento
        ↓
MOTOR DETERMINISTA
        ↓
estado + evento canónico
        ↓
CONTEXT BOX BUILDER
        ↓
GUS SANDBOX
        ↓
respuesta estructurada
        ↓
VALIDADOR
        ↓
voz / emoción / animación / candidatos de memoria
```

El camino inverso hacia el motor NO existe.

## Context Box mínimo

Debe incluir capas, no un dump:

1. `identity`
2. `canonical_state`
3. `stat_trends`
4. `recent_events`
5. `episodic_memories`
6. `relationship`
7. `preferences_and_habits`
8. `conversation_digest`
9. `open_threads`
10. `environment`
11. `model_context`
12. `guardrails`

Ver `04_CONTEXT_BOX_SPEC.md`.

## Resultado mínimo aceptable

En un teléfono físico compatible:

1. Crear/cargar criatura existente.
2. Descargar/importar un modelo local o elegir uno ya disponible.
3. Hablarle sin internet.
4. GUS responde como esa criatura.
5. Cerrar la app.
6. Cambiar stats mediante cuidados reales.
7. Reabrir horas después.
8. GUS recibe el estado actualizado y recuerda al menos un episodio anterior relevante.
9. Cambiar de modelo local.
10. La identidad/memoria de la criatura permanece porque vive en el save/contexto, no dentro del GGUF.
11. Desactivar/eliminar GUS.
12. El juego continúa con fallback local.

## Gates

### Gate A — baseline
Tests y builds actuales documentados antes de cambios.

### Gate B — context
Context Box serializa, migra, limita tamaño y no contiene secretos.

### Gate C — authority
Prueba negativa: ninguna salida del modelo puede modificar `World`/stats directamente.

### Gate D — iOS local
Inferencia real en teléfono físico o estado explícito `NOT_DEMONSTRATED`.

### Gate E — Android local
Inferencia real en teléfono físico o estado explícito `NOT_DEMONSTRATED`.

### Gate F — continuity
Reinicio + cambio de modelo conserva identidad/memorias.

### Gate G — fallback
Sin modelo, sin internet y con error del runtime, TamagotchIA sigue jugable.

## Artefactos esperados

- código;
- tests;
- schema versionado de Context Box;
- migración de saves;
- documentación de privacidad y backup;
- matriz iOS/Android/PWA;
- evidencia de device tests;
- lista de claims DEMONSTRATED / INFERRED / NOT_DEMONSTRATED;
- rollback claro.

## Stop conditions

Detente y reporta antes de continuar si:

- integrar llama.cpp obliga a reescribir el motor del juego;
- la licencia de un componente/modelo no permite el uso esperado;
- se requiere exponer filesystem o red para que “funcione” el GUS local;
- la única forma de continuidad es guardar prompts/transcripts ilimitados;
- la rama actual diverge tanto que el paquete ya no describe el sistema.

## Rollback

La integración debe poder deshabilitarse con feature flag/config y volver a:

```text
motor + persona remota opcional + fallback local
```

sin migración destructiva del save.
