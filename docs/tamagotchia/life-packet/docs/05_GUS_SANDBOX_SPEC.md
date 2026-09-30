# 05 — GUS Sandbox

## Objetivo

Permitir que el modelo “viva” como mente/persona sin convertirlo en agente general con autoridad.

## Interfaz conceptual

```ts
type MindTrigger =
  | { kind: "talk"; text: string }
  | { kind: "game_event"; eventId: string }
  | { kind: "return"; absenceMs: number }
  | { kind: "reflection" }
  | { kind: "battle"; battleContext: unknown };

interface CreatureMind {
  generate(
    context: ContextBoxV1,
    trigger: MindTrigger,
    signal?: AbortSignal
  ): Promise<MindReplyV1>;
}
```

## MindReplyV1

El contrato actual `PersonaReply` es una base excelente. Extender sólo si se demuestra necesidad.

Propuesta:

```json
{
  "speech": "Pensé que ya no ibas a volver. Tengo hambre, por cierto.",
  "emotion": "grumpy",
  "intent": "request_food",
  "animation": "side_eye",
  "memory_candidates": [],
  "thread_candidates": [],
  "debug": null
}
```

No incluir `new_hunger`, `give_item`, `heal`, `xp_delta`, etc.

## Sandbox de datos

El modelo recibe una copia serializada del Context Box. No recibe referencias mutables a objetos del juego.

### Modo local

- sin red;
- sin filesystem general;
- sólo lectura del modelo GGUF mediante runtime nativo;
- sólo salida textual/estructurada hacia el validator.

### Modo remoto

Puede usar red exclusivamente hacia el proveedor configurado, como ya hace la capa de voz actual. El mismo contrato de salida debe aplicar.

### PWA

Puede mantener providers remotos/fallback. Si WebGPU/wasm local se añade algún día, debe ser un adapter separado, no requisito de V1.

## Fail closed

Si ocurre:

- timeout;
- JSON inválido;
- crash del runtime;
- modelo ausente;
- contexto demasiado grande;
- output fuera de schema;
- token loop;

entonces:

```text
GUS falla
  ↓
validator/recovery
  ↓
fallback local de la criatura
  ↓
el juego continúa
```

## Sampling

Chat/persona puede usar sampling estable y anti-repetition. Benchmarks, classifiers o tests reproducibles pueden mantener greedy por separado.

No mezclar parámetros de UX con parámetros de benchmark.

## Crash forensics

Para local inference registrar sólo metadatos técnicos mínimos:

- model id/hash;
- phase: load/prefill/generate;
- token counts;
- memory footprint si está disponible;
- thermal state si está disponible;
- abnormal termination marker.

Nunca prompt completo ni respuesta completa en crash logs por defecto.

## Autoridad

La frontera final es:

```text
GUS proposes language/memory
code decides persistence
engine decides reality
```
