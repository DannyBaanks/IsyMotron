# 08 — Contrato futuro de combate / PvP

**No implementar como parte del primer GUS merge.** Este documento evita diseñar el Context Box de manera que cierre esa puerta.

## Idea

El cuidado real crea stats y rasgos. GUS aporta personalidad e intención táctica. El motor de combate resuelve resultados.

```text
crianza real
   ↓
stats/rasgos canónicos
   ↓
BattleProfile
   ↓
GUS propone intención
   ↓
Battle Engine determinista
   ↓
receipt/replay
   ↓
GUS recuerda la pelea
```

## Nunca

No pedir al LLM “decide cuánto daño hizo”.

## BattleIntent

Ejemplo:

```json
{
  "stance": "aggressive",
  "move_id": "pounce",
  "flavor": "No pienso perder otra vez contra ese gato."
}
```

El motor valida `move_id` y calcula todo.

## PvP local futuro

Transportes posibles por plataforma deben investigarse cuando toque. En Apple, una opción natural es peer-to-peer local mediante APIs nativas; Android requerirá su propio transporte o una abstracción compatible.

El protocolo no debe depender del transporte.

### Handshake

- creature profile hash;
- ruleset version;
- seed negotiation;
- move set;
- session id.

### Reproducibilidad

```text
initial_state
+ ruleset_version
+ seed
+ ordered_actions
= deterministic final_state
```

Guardar receipt para replay/debug.

## PvP remoto futuro

Cuando exista host:

```text
client A → authoritative host ← client B
```

El host resuelve y firma/retorna resultados. Los clientes no son autoridad final.

## Memoria de rivales

`battle_history` puede alimentar Context Box con:

- rival id/display name;
- wins/losses;
- último encuentro;
- eventos memorables;
- rivalries resumidas.

Así GUS puede reconocer a un rival sin que esa memoria altere las reglas.
