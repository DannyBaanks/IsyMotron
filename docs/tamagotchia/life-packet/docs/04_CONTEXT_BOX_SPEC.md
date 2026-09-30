# 04 — Context Box V1

## Qué es

Un snapshot pequeño, explícito y versionado de **lo que GUS necesita saber ahora**.

No es:

- el save entero;
- el transcript entero;
- un vector DB obligatorio;
- memoria secreta del modelo;
- una vía para que el modelo escriba el mundo.

## Capas

### 1. identity

Datos casi permanentes:

- `creature_id`
- nombre
- especie
- etapa
- fecha de nacimiento/adopción
- rasgos base
- identidad narrativa corta

### 2. canonical_state

Snapshot actual, sólo lectura:

- hunger
- energy
- mood
- health
- cleanliness
- bond
- asleep/sick
- XP/etapa si ya existen en el modelo real
- condiciones derivadas

### 3. stat_trends

No sólo “hambre=32”; también contexto temporal calculado por código:

- `hunger_delta_6h`
- `mood_delta_24h`
- `care_streak_days`
- `neglect_minutes_recent`
- `feeds_24h`
- `plays_24h`
- `sleep_quality_recent`
- `sick_events_7d`

Los nombres finales deben adaptarse a stats reales. Evitar guardar muestras cada minuto. Guardar agregados/buckets.

### 4. recent_events

Últimos eventos importantes, por ejemplo 8–20:

```json
{
  "kind": "fed",
  "at": 1790791200000,
  "summary": "Danny le dio pescado y lo aceptó feliz"
}
```

No volcar payloads enormes.

### 5. episodic_memories

Memorias importantes a largo plazo:

- nacimiento;
- evolución;
- primera comida favorita;
- enfermedad/recuperación;
- ausencia prolongada;
- objeto especial;
- victoria/derrota memorable futura;
- momento conversacional saliente.

Cada memoria debe tener:

- id;
- timestamp;
- tipo;
- resumen;
- saliencia;
- fuente/provenance;
- opcionalmente decay/pinning.

### 6. relationship

Resumen estructurado de relación, calculado desde hechos:

```json
{
  "bond_level": 78,
  "care_style": "constante y juguetón",
  "trust_summary": "vuelve cuando estoy enfermo y juega mucho conmigo",
  "recent_tension": null
}
```

El LLM puede proponer lenguaje, pero los números vienen del motor.

### 7. preferences_and_habits

- comida favorita/rechazada;
- juguetes preferidos;
- horarios típicos;
- actividad frecuente;
- aversiones demostradas;
- rasgos aprendidos si existen.

Distinguir `DEMONSTRATED_BY_GAME` de `MODEL_INFERRED`.

### 8. conversation_digest

Resumen compacto de conversaciones, no transcript eterno.

Ejemplo:

```json
{
  "summary": "Danny contó que hoy estuvo ocupado; Malbolgato se burló de que volvió tarde.",
  "last_user_topics": ["trabajo", "volver tarde"],
  "last_updated_at": 1790791800000
}
```

Mantener opcionalmente 2–6 turnos recientes crudos sólo para coherencia inmediata.

### 9. open_threads

Cosas que pueden retomarse después:

```json
[
  {
    "id": "thread_12",
    "summary": "Danny prometió jugar Atrapa la estrella después",
    "created_at": 1790791800000,
    "expires_at": 1790878200000,
    "source": "conversation"
  }
]
```

El código valida, expira y limita cantidad.

### 10. environment

- hora local / daypart;
- cuánto tiempo pasó desde última visita;
- conectividad si es relevante;
- modo offline;
- contexto de escena actual.

No meter ubicación precisa ni datos personales salvo feature explícita futura.

### 11. model_context

- model_id;
- context budget;
- mode: local/remote/fallback;
- sampling profile;
- capabilities declaradas.

GUS debe saber sus límites sin fingir capacidades.

### 12. guardrails

Campo explícito, generado por código:

```json
{
  "may_modify_game_state": false,
  "may_use_tools": false,
  "may_access_files": false,
  "may_access_network": false,
  "reply_schema": "MindReplyV1"
}
```

## Budget sugerido

Primer objetivo: que el Context Box normal quepa cómodamente en **1–2K tokens** antes del mensaje actual.

Prioridad de poda:

1. guardrails + identity: nunca podar;
2. canonical_state: nunca podar;
3. trigger/current event: nunca podar;
4. relationship/preferences: conservar resumen;
5. memories: top-k por relevancia/saliencia;
6. recent events: recortar por antigüedad;
7. recent raw dialogue: primero en desaparecer.

## Determinismo

El `ContextBoxBuilder` debe ser testeable como función pura para una entrada dada, salvo campos de tiempo inyectados explícitamente.
