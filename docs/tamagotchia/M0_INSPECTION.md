# M0 — Inspección: TamagotchIA × ISyMotron

Solo inspección: no se tocó código de ningún repo. Fecha: 2026-09-30.
Cada afirmación lleva su etiqueta: **DEMONSTRATED** (se ejecutó o se leyó en el código), **INFERRED** (deducido, sin probar) o **NOT_DEMONSTRATED** (sin evidencia todavía).

| Repo | Ref inspeccionada |
|---|---|
| `DannyBaanks/TamagotchIA` | `main` @ `b7fe4b13383d50b1d857ae0574eb110c983157a4` (el mismo HEAD que usó el ZIP) |
| `DannyBaanks/iSyCodeMovil` | `main` @ `f6bda93` (ya incluye #6 y #7; #8 `thinking_off` sigue abierto) |
| llama.cpp | `842b1880415d6f508f03b789e5ce70194def7bfd` (el pin de iSyCode) |

---

## 1. Evidencia actual

| Hecho | Estado |
|---|---|
| `npm test`: 58/58 (engine 17, persona 18, notify 16, store 7), Node 22.22, Linux | DEMONSTRATED |
| `npm run check` (tsc) limpio; `npm run build` (vite) OK | DEMONSTRATED |
| Build iOS: hay workflow `ios.yml` (IPA sin firmar, macOS) | existe; no se corrió aquí → NOT_DEMONSTRATED en esta sesión |
| Build Android: no hay workflow en CI | NOT_DEMONSTRATED |
| El motor es puro y determinista (reloj inyectado, PRNG con semilla, `simulateElapsed` puro) | DEMONSTRATED (código + tests) |
| La persona no muta el juego: `narrate` solo devuelve palabras y cara; los comandos no esperan al LLM | DEMONSTRATED (código + tests) |
| La API key nunca entra al save ni a una exportación (va en `tamagotchia.secret.v1`) | DEMONSTRATED (código + tests) |
| La única salida de red es `OpenAICompatibleProvider` (`grep fetch` en `src/`) | DEMONSTRATED |
| El prompt de hoy: `SYSTEM_PROMPT` ≈ 1,100 caracteres + `PersonaInput` ≈ 517 caracteres (medido tras 40 h simuladas) | DEMONSTRATED (medición local) |
| El prompt de hoy cabe en un contexto de 2,048 tokens junto con los 160 de salida | INFERRED (≈1.6K caracteres ≈ 500–650 tokens; no se tokenizó) |
| Un modelo local pequeño cumple el contrato (JSON, 3–20 palabras, enums) | NOT_DEMONSTRATED |

## 2. Mapa del repo (TamagotchIA)

```text
src/engine/    verdad canónica (pura)
  types.ts       World v1, Creature, Stats (7), Traits, GameEvent, Memory
  world.ts       createWorld, emit (eventos en buffer circular de 300), trimMemories (50)
  commands.ts    applyCommand, idempotente por id de comando
  simulation.ts  simulateElapsed en pasos de 5 min, catch-up máx. 72 h, LONG_ABSENCE
  memory.ts      MemoryPolicy: rememberEvent (determinista), relevantMemories, acceptProposedMemory
  rules.ts       todos los números; derived.ts / forecast.ts / random.ts
src/persona/   voz (sin autoridad)
  contract.ts    PersonaInput, SYSTEM_PROMPT, validateReply (estricto, una reparación)
  providers.ts   PersonalityProvider, OpenAICompatibleProvider, narrate (timeout → fallback)
  fallback.ts    voz local determinista, siempre disponible
src/store/     save.ts (sobre v1 + checksum no criptográfico + backup), settings.ts (proveedor, secreto aparte)
src/notify/    notificaciones locales (único plugin nativo en uso)
src/app.ts     UI + orquestación (755 líneas)
android/, ios/App   Capacitor 8 (envuelve la PWA); CapacitorHttp activado
```

## 3. Qué reutilizaría

| Pieza | De dónde | Por qué |
|---|---|---|
| Frontera motor ↔ persona, `validateReply`, fallback, `acceptProposedMemory` | TamagotchIA (ya existe) | Es exactamente "el modelo propone, el código decide". Se **extiende**, no se reemplaza |
| `PersonaInput` como semilla del Context Box | TamagotchIA | Ya es acotado y sin secretos |
| `GUSLlamaBridge.c/.h` (chat template, neutralización de tokens de control, sampling anti-bucle, grammar en el futuro) | iSyCodeMovil `Sources/Model/` | Es un solo archivo C probado en 22 modelos por CI, con ASan limpio |
| JNI con texto en bytes UTF-8 | iSyCodeMovil `gus_jni.c` | Evita romper emojis y caracteres a medio code point |
| Catálogo generado + SHA-256 + import desde Archivos | iSyCodeMovil `Catalog/models.json` + `generate.py` | Una sola fuente de verdad: nada de dos catálogos con hashes distintos |
| Flight recorder (fase, modelo, tokens; nunca el prompt) | iSyCodeMovil | Forense de crashes sin fuga de contenido |
| Idea de `ModelContextBudget` (presupuesto medido, se poda lo viejo primero) | iSyCodeMovil #7 | Como diseño; el código Swift del agente no aplica directo al TS |
| Recibos "propone → decide → evidencia" | IsyMotron | Modelo mental para el LifeLog/receipts de M8 |

## 4. Qué NO reutilizaría y por qué

- **La UI de iSyCode Móvil:** TamagotchIA necesita solo runtime + selección de modelo, no un workbench de agente.
- **`AgentLoop` / herramientas / sandbox de archivos:** GUS no tiene herramientas en v1 (regla del Compose).
- **`ModelContextBudget.swift` tal cual:** está pensado para mensajes de agente con tool calls; el Context Box de TamagotchIA es una proyección estructurada en TS.
- **El `hashString` actual para integridad Canon:** sirve para detectar corrupción, no para receipts. Para M8 se usa WebCrypto (ver riesgo 6).
- **Los 22 modelos del catálogo desde el día 1:** primero se demuestran 1–3 modelos pequeños (el ZIP y el Compose coinciden).

## 5. Delta ZIP ↔ repo

- El contrato de persona existe y es **más estricto** que MindReplyV1 del ZIP: `speech` de 3–20 palabras contra 240 caracteres, y un solo `memory_candidate` contra arrays. Se conserva el del repo.
- De las 12 capas del Context Box, `PersonaInput` ya cubre identidad (parcial), estado canónico, evento actual, memorias top-5, favorito y hora del día.
- Faltan: `stat_trends`, `relationship`, `conversation_digest`, `open_threads`, `environment.absence`, `model_context` y `guardrails`.
- Los eventos son un buffer circular de 300, no un ledger append-only.
- El save está en v1 y **no existe código de migración**.
- No hay plugin Capacitor propio.
- El snapshot de iSyCode del ZIP (`30097a5`) está viejo.

## 6. Delta ZIP ↔ Compose

**Lo nuevo del Compose:**
- Local/Canon, "Canon nace Canon", fork a Local, `ruleset_version` e integridad.
- Interaction Gate (Context ≠ Contribution), presets y Remote Block Total.
- La costura local/remoto: el proveedor no es la identidad.
- Un `ContextBudget` explícito y el orden de lo estable a lo volátil (prefijo reutilizable).
- Salida con grammar primero.
- Memoria desde eventos, sin resúmenes del LLM en v1.
- La capa ISyMotron completa: Broker, Reviver, ISyCode como superficie de agente, MCP/OAuth, polling adaptativo, World, compute tiers.

**Documentos del ZIP que quedaron superados:**
- 04: el presupuesto de 1–2K tokens choca con un runtime de 2,048.
- 05: los arrays y los 240 caracteres.
- 06: `MODEL_SUMMARY` en v1.
- 11: el handoff ahora es [`ROADMAP.md`](ROADMAP.md).

**Sin contradicción:** 08 (PvP), porque el Compose §28 lo extiende en la misma línea.

**Gate M0.11:** ningún hallazgo contradice una premisa del Compose. La frontera de autoridad que el Compose supone **ya existe** en el repo.

## 7. Propuesta exacta de M1–M3

**M1 — contrato de datos**, en un PR chico a TamagotchIA:
1. `PetIdentity` como **vista derivada** de `Creature` (id, nombre, especie, semilla, nacimiento, rasgos): sin campos nuevos en el save y sin nada de modelo o proveedor.
2. `LifeLogEntry` = `GameEvent` + provenance (`source: "engine"`, `ruleset`). El ledger append-only de verdad se deja para M8 (ver riesgo 5).
3. `ContextBudget`: función pura `available = total − reservedOutput − system − turn`, con estimador de tokens configurable. La estimación se marca como estimación mientras no haya tokenizer nativo.
4. Tipo `ContextBoxV1` (`schema: "tamagotchia.context-box.v1"`, `guardrails` constantes, alineado con `life-packet/schemas/`).
5. Save **v2**: `world.mode: "local" | "canon"` y `world.rulesetVersion`. La migración v1→v2 marca los saves existentes como `mode: "local"`, porque nunca nacieron Canon. `validWorld` acepta v1 (y migra) y v2. El backup del v1 se conserva antes de escribir.

**M2 — compiler:**
- `compileContextBox(world, event, playerSaid, budget, now)`: pura y ordenada de lo estable a lo volátil.
- Poda por prioridad.
- Filtro de secretos: rechaza texto con forma de clave (`sk-`, `nvapi-`, `AIza`, `Bearer`, etc.).
- `personaInput` pasa a ser una proyección del Context Box, para no romper a los proveedores actuales.

**M3 — GUS local:**
- `CreatureMind` envuelve al `PersonalityProvider` actual (fallback, remoto) y agrega `NativeLocalMind` (plugin Capacitor `GusLocal`, solo si `isNativePlatform()`).
- El plugin recibe solo strings JSON.
- En iOS y Android se reutiliza el bridge C de iSyCode, **fijado por commit** (ver riesgo 3).
- La PWA muestra "GUS local requiere la app nativa".

## 8. Archivos que tocaría

- **M1:**
  - `src/engine/types.ts` (World v2: `mode`, `rulesetVersion`);
  - `src/store/save.ts` (migración, `validWorld`);
  - nuevos: `src/life/identity.ts`, `src/life/lifelog.ts`, `src/persona/budget.ts`, `src/persona/contextBox.ts`;
  - `tests/fixtures/save-v1.json`.
- **M2:**
  - nuevo `src/persona/compile.ts`;
  - `src/persona/contract.ts` (`personaInput` como proyección).
- **M3:**
  - `src/persona/providers.ts` (`CreatureMind`);
  - nuevos: `src/persona/nativeLocal.ts`, `ios/App/App/GusLocalPlugin.swift`, `android/app/src/main/java/.../GusLocalPlugin.kt`;
  - bridge C vendorizado con script de pin;
  - `.github/workflows/android.yml` (hoy no existe).
- **Aparte, al tocar cada milestone:** `SPEC.md` y `ROADMAP.md` de TamagotchIA.

## 9. Tests que agregaría

- **M1:**
  - la identidad no contiene campos de modelo o proveedor;
  - fixture v1 → migración a v2 con `mode: local`, roundtrip e idempotencia;
  - save corrupto → cae al backup;
  - `ContextBudget` nunca da negativo y respeta la salida reservada;
  - `ContextBoxV1` valida contra el schema.
- **M2:**
  - nunca excede el presupuesto;
  - prioridades estables;
  - lo irrelevante se cae primero;
  - el estado actual siempre queda;
  - texto con forma de clave nunca entra;
  - misma entrada y mismo reloj → misma salida;
  - las secciones estables van primero.
- **M3:**
  - sin plugin → fallback;
  - plugin que falla, tarda o devuelve basura → fallback sin mutar `World`;
  - cambiar de proveedor no cambia `PetIdentity` ni las memorias.

## 10. Riesgos y bloqueos

1. **Sin push a TamagotchIA** desde esta sesión: M1 necesita `add_repo access:push` (o que el usuario lo autorice). **Bloqueo para M1.**
2. **Modelos chicos contra un contrato estricto:** JSON + 3–20 palabras + enums; es probable una tasa alta de fallback sin grammar. Sin medir: NOT_DEMONSTRATED. Mitigación: M4 (GBNF existe en el llama.cpp fijado) o salida solo de `speech`.
3. **Compartir el bridge sin duplicar** (stop condition del Compose). Opciones: script de vendoring fijado a un commit de iSyCode con checksum en CI (recomendado), submódulo o paquete compartido. **Decisión del usuario.**
4. **Builds nativos:**
   - el xcframework de llama.cpp tarda unos 9 min en CI;
   - Android necesita NDK/CMake dentro del proyecto Gradle de Capacitor;
   - no hay CI de Android.
5. **Append-only contra save acotado:** hoy los eventos se descartan pasados 300. Un ledger Canon infinito rompe el presupuesto del save. Propuesta para M8: hash encadenado que cubre también lo compactado (el hash de historia sobrevive a la poda).
6. **WebCrypto es asíncrono y `save()` es síncrono:** los hashes Canon con `SubtleCrypto.digest` obligan a cambiar el flujo de guardado (M8). No se inventa criptografía.
7. **Remote Block Total:** la única salida hoy es `OpenAICompatibleProvider` (bien). Hay que mantener ese único punto de egress y probarlo con un fetcher espía. CapacitorHttp enruta `fetch` nativo, así que la prueba debe cubrir ese camino.
8. **El contexto de 2,048 hoy sobra, mañana no:** al sumar relación, tendencias y threads, sin `ContextBudget` se repite el error de iSyCode ("Prompt exceeds…").
