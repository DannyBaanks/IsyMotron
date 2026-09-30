# 06 — Memoria e historial

## Objetivo

Que GUS recuerde a la persona y su propia vida sin que el contexto crezca para siempre.

## Cuatro memorias distintas

### A. Verdad del mundo

`World` / save canónico. Nunca resumido por el modelo como fuente de verdad.

### B. Event ledger

Eventos canónicos del motor. Puede retenerse con política de compactación o límites, pero es evidencia estructurada.

### C. Episodic memory

Selección de momentos que valen la pena recordar.

### D. Conversation memory

Resumen de conversación y open threads. No confundir con eventos del juego.

## Regla de escritura

El modelo puede **proponer**, no insertar directamente.

```text
MindReply.memory_candidate
       ↓
MemoryPolicy
       ↓
validación de longitud/tipo/duplicado/saliencia
       ↓
accepted | rejected
```

## Saliencia sugerida

Puntos por hechos observables:

- nacimiento/evolución: muy alta;
- enfermedad/recuperación: alta;
- primera vez de algo: alta;
- cambio de favorito: media/alta;
- usuario comparte algo personal y explícitamente memorable: media;
- charla casual repetitiva: baja;
- spam de mimos/comida: normalmente baja.

No almacenar automáticamente secretos, API keys, tokens o texto que parezca credencial.

## Resumen conversacional

Después de N turnos o al superar presupuesto:

```text
recent raw turns
    ↓
summary candidate
    ↓
local deterministic checks
    ↓
conversation_digest replacement
```

Opcionalmente el propio GUS puede generar el resumen, pero:

- el resumen se marca como `MODEL_SUMMARY`;
- nunca sustituye datos canónicos;
- se puede regenerar/borrar;
- está sujeto a longitud máxima.

## Historial de stats

No guardar un snapshot por tick.

Guardar agregados por ventanas:

- 1h/6h/24h/7d según necesidad;
- mínimos/máximos;
- deltas;
- counts de acciones;
- rachas;
- incidentes significativos.

Esto le permite al GUS decir “últimamente duermo poco” sin recibir miles de muestras.

## Decay

- pinned memories: no decaen;
- episodios fuertes: decaimiento lento;
- detalles triviales: expiran;
- open threads: tienen TTL;
- raw conversation: buffer pequeño.

## Backup

El backup de criatura debe incluir:

- Context Box state derivable o sus fuentes;
- episodic memories;
- relationship summary;
- conversation digest;
- open threads;
- schema versions.

No debe incluir:

- API keys;
- modelo GGUF de varios GB;
- tokens del proveedor;
- crash logs completos salvo export explícito.
