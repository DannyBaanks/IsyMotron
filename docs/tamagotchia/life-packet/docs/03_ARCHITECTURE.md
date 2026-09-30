# 03 — Arquitectura propuesta

## Separación de responsabilidades

```text
┌──────────────────────────────────────────────┐
│                 TAMAGOTCHIA                  │
│                                              │
│  Player action / elapsed time                │
│                │                             │
│                ▼                             │
│        Deterministic Game Engine             │
│                │                             │
│      canonical World + GameEvent             │
│                │                             │
│                ▼                             │
│          Context Box Builder                 │
│                │                             │
│        immutable snapshot                    │
│                ▼                             │
│             GUS Sandbox                      │
│      ┌──────────┼──────────┐                 │
│      │          │          │                 │
│   fallback    remote     local GGUF           │
│                           │                  │
│                    llama.cpp native           │
│                │                             │
│                ▼                             │
│          MindReply Validator                 │
│                │                             │
│     ┌──────────┴──────────┐                  │
│     ▼                     ▼                  │
│ speech/animation      memory proposal         │
│                           │                  │
│                           ▼                  │
│                    Memory Policy              │
└──────────────────────────────────────────────┘
```

## Regla de autoridad

### Motor puede

- modificar stats;
- decidir enfermedad;
- decidir evolución;
- decidir recompensas;
- decidir inventario;
- resolver combate;
- crear eventos canónicos.

### GUS puede

- hablar;
- elegir emoción/animación permitida;
- interpretar el estado;
- proponer una memoria;
- mantener un resumen de relación/conversación;
- proponer intención táctica futura;
- reaccionar a la historia.

### GUS no puede

- ejecutar comandos del motor;
- escribir el save arbitrariamente;
- inventar un objeto y añadirlo;
- curarse;
- cambiar una estadística;
- dar XP;
- alterar timestamps;
- tocar filesystem externo;
- abrir red en modo local;
- usar herramientas del dispositivo.

## “Vivir” sin inferencia 24/7

No hace falta tener el modelo generando todo el tiempo para que la criatura se sienta viva.

La continuidad proviene de:

```text
persistencia del mundo
+ historial estructurado
+ Context Box
+ invocaciones en momentos significativos
```

Triggers sugeridos:

- `player_talk`
- `feed`
- `play`
- `pet`
- `wake`
- `sleep`
- `sick`
- `recover`
- `evolve`
- `return_after_absence`
- `discover_item`
- `relationship_milestone`
- futuro: `battle_start`, `battle_turn`, `battle_end`

Opcional futuro: pensamientos idle de baja frecuencia, nunca necesarios para mantener el estado.

## Estado del modelo vs estado de la criatura

No mezclar:

```text
Creature Save
- identidad
- stats
- memoria
- relación
- contexto
- historia

Model Installation
- model_id
- GGUF path
- sha256
- runtime settings
- benchmark/fit
```

Cambiar/borrar el GGUF no borra la personalidad histórica de la criatura.
