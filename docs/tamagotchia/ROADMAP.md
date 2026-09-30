# Roadmap — TamagotchIA × ISyMotron (handoff vivo)

Esta lista es el handoff. Cualquier agente (Claude, Codex, OpenISy) que llegue a
media obra empieza aquí. Las tareas se tachan cuando están **hechas y
verificadas**, y cada tachado va en su propio commit con push.

**Fuentes, en este orden:**
1. El repo real (siempre manda).
2. [`COMPOSE.md`](COMPOSE.md): decisiones del 2026-09-30, extiende el ZIP.
3. [`life-packet/`](life-packet/): el paquete ZIP original (GUS + Context Box + memoria).

---

## Cómo retomar (léelo antes de tocar nada)

1. Busca abajo la primera casilla `[ ]` sin tachar: esa es la siguiente tarea.
2. Revisa **Estado actual** y el **Registro de provenance** al final.
3. Trabaja en tareas chicas. Al terminar cada una:
   - verifica (tests, build o evidencia);
   - tacha la casilla `[x]`, escribe en una línea qué se hizo y dónde está la evidencia;
   - agrega una fila al registro de provenance;
   - haz commit y push de inmediato. Si la sesión se corta, lo tachado ya está en GitHub.
4. Una tarea a medias no se tacha. Anota `(en curso: …)` al lado y haz commit igual.
5. Clasifica lo que afirmes como **DEMONSTRATED**, **INFERRED** o **NOT_DEMONSTRATED**.
6. No declares "funciona en iPhone/Android" sin prueba en hardware físico.
   No uses "anti-cheat" si solo existe un hash local, ni "privado" si un proveedor remoto recibió contexto.

**Dónde vive cada cosa:**

| Qué | Repo | Rama |
|---|---|---|
| Este roadmap, COMPOSE, paquete | `DannyBaanks/IsyMotron` | `claude/exciting-lamport-84gclk` |
| Código del juego (M1–M8) | `DannyBaanks/TamagotchIA` | `claude/gus-life-m1` (M1; sin PR hasta que el usuario lo pida) |
| Runtime GUS a reutilizar | `DannyBaanks/iSyCodeMovil` | `main` |
| Reviver (M9) | Munder | **solo lectura y solo si el usuario lo autoriza** |

## Estado actual

- **Milestone activo:** M3. M0, M1, M2, M3.1 y M3.2 están hechos; el código vive en TamagotchIA `claude/gus-life-m1` (99 tests, sin PR hasta que el usuario lo pida).
- **Decidido (2026-09-30):** para M3.3/M3.4 se usa copia fijada del bridge ([`COMPOSE_M3_VENDOR.md`](COMPOSE_M3_VENDOR.md)). El egress remoto sigue fail-closed hasta M5.
- **Decisión pendiente del usuario (para M3):** cómo compartir el bridge C de iSyCode (vendoring fijado a un commit, submódulo o paquete).
- **Acceso:** TamagotchIA está adjunto con push (clon en `/home/user/tamagotchia`). Antes de correr tests: `npm ci`.
- **iSyCodeMovil #8 (`thinking_off`) mergeado.** Smoke con build portable: los 22 modelos corren y ninguno se queda a medio `<think>` (`unfinished_think: false` en todos). Qwen3 4B/8B contestan Vicente Fox; Qwen3 0.6B y Nemotron Nano 4B contestan pero inventan. Para TamagotchIA: `thinking_off` ya está en el catálogo de `main`.

---

## Reglas que no se rompen

- El modelo propone; el motor del juego decide; queda historia verificable.
- GUS nunca escribe stats, inventario, XP, evolución, timestamps, cooldowns ni progreso Canon.
- La mascota no es el modelo: identidad y memoria viven en el save, no en el GGUF ni en el proveedor.
- Si GUS falla, el juego sigue con un fallback determinista. La PWA sigue jugable sin runtime nativo.
- Nada de transcripts infinitos. Los recuerdos verificables salen de eventos reales, no de resúmenes del LLM.
- Canon nace Canon. Canon → copia Local sí; Local → Canon nunca.
- No se inventa criptografía: se usa la del sistema (WebCrypto / CryptoKit / Android Keystore).
- Remote Block Total significa **cero** tráfico a inteligencia remota.
- Los secretos (API keys, tokens, credenciales) nunca entran al Context Box.
- No se reescribe historia de releases ni attestations de IsyMotron.
- Nada de PRs gigantes ni refactors ajenos. Si hay que ampliar permisos o autoridad, se detiene el trabajo y se reporta.

---

## H — Handoff

- [x] **H1** Guardar el Compose y el paquete ZIP en el repo. → `docs/tamagotchia/COMPOSE.md`, `docs/tamagotchia/life-packet/` (los checksums del MANIFEST coinciden).
- [x] **H2** Crear este roadmap con las reglas de tachado y retoma.

## M0 — Inspección (sin tocar código)

Entrega: `docs/tamagotchia/M0_INSPECTION.md` con los 10 puntos de la sección 43 del Compose.

- [x] **M0.1** Acceso de lectura a `DannyBaanks/TamagotchIA`; registrar rama, HEAD y fecha. → repo público, clon de solo lectura; `main` @ `b7fe4b13383d50b1d857ae0574eb110c983157a4` (2026-09-25), el mismo HEAD que usó el ZIP. Push al repo NO disponible en esta sesión.
- [x] **M0.2** Correr los tests y el build actuales (`npm test` / `check` / `build` o equivalentes); registrar resultados reales. → Node 22.22: `npm test` 58/58 en 4 archivos (engine 17, persona 18, notify 16, store 7); `npm run check` limpio; `npm run build` OK. Builds nativos no corridos aquí (hay workflows `ios.yml` y `pages.yml`, pero ninguno de Android): NOT_DEMONSTRATED.
- [x] **M0.3** Mapear engine, persona, memory, store, providers, UI y Capacitor iOS/Android, con paths reales.
  - → Mapa: `src/engine/` (types, world, commands, simulation, rules, memory, derived, forecast, random; puro, reloj inyectado y PRNG con semilla), `src/persona/` (contract, providers, fallback), `src/store/` (save, settings), `src/notify/` (plan, alerts, deliver, native), `src/app.ts` (755 líneas: UI + orquestación). Capacitor 8 con `android/` e `ios/App`; CapacitorHttp activado; el único plugin nativo en uso es LocalNotifications. No existe plugin nativo propio ni inferencia local: la persona es solo remota (OpenAI-compatible). DEMONSTRATED (lectura de código).
- [x] **M0.4** Formato del save: versión, migraciones existentes y fixtures.
  - → Save: sobre `{format:"tamagotchia-save", version:1, savedAt, checksum, world}` en localStorage (`tamagotchia.save.v1` + `.bak`, que solo guarda un save bueno); `validWorld` revisa la forma; export/import usan el mismo sobre. El checksum es `hashString`: detecta corrupción, NO es criptográfico. La API key vive en `tamagotchia.secret.v1` y nunca entra al save. **No hay código de migración** (solo existe la versión 1). Historia acotada: eventos en un buffer circular de 300 (`MAX_EVENTS`), memorias hasta 50, comandos procesados 200. Por eso hoy la historia NO es append-only, lo cual importa para M8/Canon.
- [x] **M0.5** Contrato de persona actual (`personaInput`, `PersonaReply`, prompt) contra MindReplyV1 del ZIP.
  - → `PersonaInput` ya es un Context Box mínimo: nombre, especie, etapa, evento, stats, condiciones, rasgos, comida favorita, hasta 5 memorias, hora del día y `player_said` (limpio, máx. 80 caracteres). `PersonaReply`: `speech` de 3 a 20 palabras + emoción/intención/animación de listas cerradas + un solo `memory_candidate`. `validateReply` es estricto con una sola reparación; el fallback es determinista; `narrate` tiene timeout. `acceptProposedMemory` ya implementa "el modelo propone, el código decide" (4 a 80 caracteres, ligada al evento, máx. 10 activas, TTL de 7 días). Frente a MindReplyV1 del ZIP: el contrato del repo es más estricto y conviene conservarlo como base. Le faltan relación, tendencias, digest de conversación, open threads, ausencia/entorno, model_context y guardrails.
- [x] **M0.6** Qué se reutiliza de iSyCode Móvil, verificado en `main`:
  - contexto: 2048 y 4096 soportados por `gus_llama_create`;
  - `ModelContextBudget` (PR #7);
  - sampling anti-bucle (PR #6);
  - `thinking_off` (PR #8);
  - texto UTF-8 como bytes en JNI;
  - catálogo + SHA-256 + import desde Archivos;
  - flight recorder.
  - → Verificado en iSyCodeMovil `main` @ `f6bda93` (licencia MIT):
    - `gus_llama_create` acepta de 512 a 4096 tokens de contexto;
    - el sampling anti-bucle (#6) y `ModelContextBudget` (#7) ya están mergeados;
    - `thinking_off` (#8) **todavía no está en main**: el PR sigue abierto;
    - JNI pasa el texto como bytes UTF-8 (`gus_jni.c`);
    - catálogo con SHA-256 y descarga/import (`GUSModelDownloadManager`, `ModelStore.kt`);
    - flight recorder en iOS y Android.
    Hay que reutilizar el bridge C y el catálogo generado desde `Catalog/models.json`, **no copiar la UI**. El Context Box de TamagotchIA se arma en TS; `ModelContextBudget` (Swift, pensado para el agente) sirve solo como referencia de diseño.
- [x] **M0.7** Grammar / constrained decoding en el commit fijado de llama.cpp: ¿existe `llama_sampler_init_grammar`? ¿Compila en iOS y Android? (se investiga, no se implementa).
  - → En el llama.cpp fijado (`842b188`) existe `llama_sampler_init_grammar(vocab, gbnf, root)` (y `_lazy_patterns`). `llama-grammar.cpp` es parte de la librería `llama` (`src/CMakeLists.txt`) y sus símbolos están en el `libllama.a` de Linux (`nm`): DEMONSTRATED en Linux. Que entre en el xcframework de iOS y en el `.so` de Android: INFERRED (mismo target `llama`; no se compiló aquí). El bridge no lo usa todavía: habría que agregar un parámetro de grammar a `make_sampler`, al inicio de la cadena. Si la grammar no parsea, llama.cpp devuelve NULL: fallar cerrado y usar el fallback.
- [x] **M0.8** Reutilizar el prefijo (KV) en el bridge: hoy `generate` llama `llama_memory_clear` en cada respuesta. Documentar qué haría falta, sin hacks.
  - → Reutilizar el prefijo es factible sin hacks: `llama_memory_seq_rm(mem, 0, n_común, -1)` quita solo la cola, y así se decodifica únicamente lo nuevo. Hace falta:
    1. guardar en `GUSLlamaContext` los tokens del prompt anterior;
    2. calcular el prefijo común;
    3. llamar `seq_rm` en vez de `llama_memory_clear`.
    Restricción: en modelos recurrentes o híbridos (p. ej. Nemotron-H/Mamba) `seq_rm` parcial puede devolver false; ahí se hace un clear completo. Aprovecharlo exige que el Context Box vaya de lo estable a lo volátil (M2.3). No hay números de ahorro: sin benchmark, NOT_DEMONSTRATED.
- [x] **M0.9** Deltas: ZIP ↔ repo, ZIP ↔ Compose y documentos que quedaron viejos.
  - → **ZIP ↔ repo:**
    - El contrato de persona sí existe y es más estricto que MindReplyV1.
    - `PersonaInput` cubre identidad parcial, estado canónico, evento actual, memorias top-5, favorito y hora. Le faltan stat_trends, relationship, conversation_digest, open_threads, model_context, guardrails y los minutos de ausencia (aunque existe el evento `LONG_ABSENCE`).
    - Los eventos son un buffer circular de 300, no un ledger.
    - Save v1 sin migraciones.
    - No hay plugin Capacitor propio.
    - El snapshot de iSyCode del ZIP (`30097a5`) está viejo: `main` ya lleva #6 y #7.

    **ZIP ↔ Compose:** el Compose agrega:
    - Local/Canon, "Canon nace Canon" y `ruleset_version`/integridad;
    - Interaction Gate (context ≠ contribution), presets y Remote Block Total;
    - la costura local/remoto (el proveedor no es la identidad);
    - un `ContextBudget` explícito y el orden de estable a volátil;
    - salida con grammar primero;
    - memoria desde eventos, sin resúmenes del LLM en v1;
    - la capa ISyMotron (Broker, Reviver, ISyCode agente, MCP/OAuth, polling adaptativo, World, compute).

    **Quedaron superados en el ZIP:**
    - 04 (presupuesto de 1–2K tokens);
    - 05 (`memory_candidates`/`thread_candidates` como arrays y `speech` de 240 caracteres);
    - 06 (permitía `MODEL_SUMMARY` en v1);
    - 11 (el handoff ahora es este ROADMAP).

    **En TamagotchIA:** `SPEC.md` y `ROADMAP.md` no mencionan GUS local, Canon ni el gate; habrá que actualizarlos cuando se toque cada milestone, no antes.
- [x] **M0.10** Escribir `M0_INSPECTION.md`:
  1. evidencia;
  2. mapa del repo;
  3. qué se reutiliza;
  4. qué NO se reutiliza y por qué;
  5. delta ZIP ↔ repo;
  6. delta ZIP ↔ Compose;
  7. propuesta exacta de M1–M3;
  8. archivos a tocar;
  9. tests a agregar;
  10. riesgos y bloqueos.
  - → [`M0_INSPECTION.md`](M0_INSPECTION.md) con los 10 puntos. Medición nueva: `SYSTEM_PROMPT` ≈ 1,100 caracteres + `PersonaInput` ≈ 517 caracteres tras 40 h simuladas; hoy cabe en 2,048 tokens (INFERRED, sin tokenizar).
- [x] **M0.11** Gate: si M0 contradice el Compose, detenerse y reportar. Si está limpio, seguir con el slice mínimo de M1.
  - → Gate limpio: nada del repo contradice el Compose; la frontera de autoridad ya existe. Seguir con M1. Bloqueos: (a) M1 necesita push a TamagotchIA; (b) M3 necesita que el usuario decida cómo compartir el bridge C (vendoring fijado recomendado; ver riesgo 3).

## M1 — Contrato de datos (TamagotchIA, tests primero)

- [x] **M1.1** `PetIdentity`: id estable, especie, rasgos iniciales, nacimiento. Sin ningún campo de modelo o proveedor.
  - → `src/life/identity.ts`: `petIdentity(world)` es una vista derivada y copiada (id, nombre, especie, semilla, nacimiento, eclosión, etapa, rasgos). No agrega campos al save y no tiene nada de modelo o proveedor. Tests en `tests/life.test.ts`: la forma no tiene campos de modelo, la identidad es estable tras un comando y escribir en la vista no llega al world. Suite 61/61, tsc limpio. Commit `9b1070a`.
- [x] **M1.2** `LifeLog`: evento con provenance (fuente, timestamp, versión del ruleset); append-only.
  - → `src/life/lifelog.ts`: `lifeLog(world)` convierte cada evento del motor en una entrada con `provenance {source: "engine", ruleset}`. `RULESET_VERSION = "tamagotchia-rules-1"` vive en `rules.ts`. Honestidad: el save conserva solo los últimos 300 eventos, así que el log es la ventana retenida y reporta `droppedBefore` en vez de fingir que es la vida completa. El append-only real, con hash que sobreviva a la poda, queda para M8. Tests: orden y provenance, aviso de poda tras 320 eventos, y que la copia no escribe al world. Suite 64/64, tsc limpio. Commit `c40fa59`.
- [x] **M1.3** `ContextBudget`: `total − salida reservada − contrato del sistema − turno actual = contexto disponible para la mascota`.
  - → `src/persona/budget.ts`: `contextBudget()` (nunca negativo, con `fits:false` cuando lo fijo ya no cabe; entradas absurdas cuentan como 0) + `estimateTokens()`, que es una ESTIMACIÓN pesimista de 2.5 caracteres por token contando code points, hasta tener tokenizer nativo (M3). Test clave: el prompt de hoy cabe en 2,048 con 160 de salida y deja más de 800 tokens libres (con la estimación). Suite 69/69, tsc limpio. Commit `4c1e85b`.
- [x] **M1.4** Schema `ContextBox` v1, versionado y alineado con `life-packet/schemas/`.
  - → `src/persona/contextBox.ts`: tipo `ContextBoxV1` (snake_case, alineado con el schema del paquete), `GUARDRAILS` congelado que no concede nada a ningún cerebro (tampoco red), y `validateContextBox` que falla cerrado: rechaza campos extra, schema desconocido, listas grandes (20/20/8), permisos concedidos y cualquier cosa con forma de credencial. Diferencia con el paquete: su ejemplo tenía `may_access_network: true`; aquí siempre es false, porque la red la usa el proveedor, no GUS. El `reply_schema` apunta al `PersonaReply` actual. Suite 73/73, tsc limpio. Commit `e40c89a`.
- [x] **M1.5** Marcador `mode: local | canon` + `ruleset_version` en el save, con migración no destructiva.
  - → World v2: `mode: "local" | "canon"` + `rulesetVersion`; `createWorld(..., mode = "local")`. La migración v1→v2 al cargar o importar: (a) siempre queda `local`, aunque el archivo v1 diga `canon` (los campos forzados van al final); (b) el checksum se verifica sobre el world tal como se escribió; (c) el primer save v1 leído se guarda intacto en `tamagotchia.save.v1.premigration` (una sola vez, nunca se sobrescribe) para poder volver a un build viejo. Los comandos no cambian ni el modo ni el ruleset. Tests en `tests/migration.test.ts`. Suite 80/80, tsc y build OK. Commit `318ed2d`.
- [x] **M1.6** Fixtures del save anterior, test de migración, roundtrip y manejo de entradas corruptas.
  - → Fixture real `tests/fixtures/save-v1.b7fe4b1.json`, escrito por el build v1 sin modificar (`b7fe4b1`, 24 h de cuidados, `exportSave`). Tests: migra a v2 local conservando criatura, eventos y memorias; roundtrip y sigue jugando; si el save principal está cortado, se recupera del backup v1; la basura nunca carga ni truena. **Bug encontrado que ya existía en main:** un sobre sin `world` truena en `hashString` y rompe la promesa "loading never throws" (reproducido en el clon de `b7fe4b1`). Arreglado: ahora devuelve un problema. Suite 84/84, tsc limpio. Commit `e0a7867`.

## M2 — Context compiler

- [x] **M2.1** Compilar el Context Box desde el estado, como función pura con reloj inyectado.
  - → `src/persona/compile.ts`: `compileContextBox({world, now, budgetTokens, model?})` es pura (reloj inyectado; nada de settings ni red) y devuelve una caja válida + tokens + `fits` + `dropped`. El turno actual (evento + lo que dijo el jugador) queda **fuera** de la caja, como mensaje propio. `stat_trends` se omite en vez de inventarse, porque el motor todavía no guarda agregados. Nota: `timeOfDay` usa la hora local del aparato, así que es determinista por zona horaria. Commit `129644f`.
- [x] **M2.2** Prioridades: contrato > identidad > estado actual > evento > recuerdos relevantes > relación > historia > detalles.
  - → Poda de lo menos importante a lo más: eventos recientes (los más viejos primero) → preferencias → relación → memorias (las menos salientes primero). Contrato, identidad y estado actual nunca se podan; si ni eso cabe, `fits:false` y no se llama al modelo. Los hitos (saliencia 1) van primero.
- [x] **M2.3** Orden de lo estable a lo volátil, para poder reutilizar el prefijo más adelante.
  - → Orden de llaves de lo estable a lo volátil: `schema, guardrails, identity, preferences, episodic_memories, relationship, recent_events, canonical_state, environment, model_context, generated_at`. Test: dos momentos de la misma vida comparten el prefijo hasta `preferences_and_habits` (base para reutilizar KV, M0.8).
- [x] **M2.4** Tests:
  - nunca excede el presupuesto;
  - las prioridades son estables;
  - lo irrelevante se cae primero;
  - el estado actual siempre queda;
  - los secretos nunca entran;
  - misma entrada, misma salida.
  - → `tests/compile.test.ts` (8 tests): caja válida completa; nunca excede el presupuesto y respeta el orden de poda; el núcleo se conserva con presupuesto 1; memorias por saliencia; determinismo; prefijo estable; credenciales filtradas (memoria propuesta con `sk-…` y nombre `nvapi-…`); no toca el world. Suite 92/92, tsc limpio.

## M3 — GUS local

- [x] **M3.1** Interfaz `CreatureMind` / `GUSProvider` con implementaciones fallback, remoto existente y local (placeholder).
  - → `src/persona/mind.ts`: `CreatureMind {name, kind: fallback|remote|local, respond(request, signal) → texto}` + `remoteMind(provider)`; `speak()` en providers.ts valida o cae al fallback; `narrate` ahora pasa por `speak` sin cambiar comportamiento (los 18 tests de persona siguen pasando). **Decisión de seguridad:** el cerebro remoto sigue recibiendo solo el turno, como antes; la Context Box va únicamente al cerebro local hasta que M5 defina la proyección remota, así esta costura no amplía lo que sale del aparato. Tests en `tests/mind.test.ts`: remoto sin caja, local con caja, salida mala o tramposa o crash → fallback sin tocar el world, y cambiar de cerebro no cambia la identidad. Suite 96/96. Commit `67de840`.
- [x] **M3.2** Frontera del plugin Capacitor. Recibe solo strings/JSON del Context Box, nunca `World` mutable.
  - → Lado TS listo. `src/persona/localMind.ts`: el plugin `GusLocal` expone una sola llamada, `generate({system, context, turn, maxTokens})`, con 3 strings y un tope de 160 tokens. La caja se valida antes; si es inválida o trae algo con forma de credencial, nunca llega al runtime. Si el runtime falla, se cuelga o no devuelve texto → fallback. `src/persona/nativeGus.ts` devuelve null fuera de la app nativa, así que la PWA no cambia. **Pendiente:** conectarlo a la UI (con M3.5) y el lado nativo (M3.3/M3.4). Tests en `tests/localMind.test.ts`. Suite 99/99, tsc y build OK. Commit `4a59e0a`.
- [ ] **M3.3** Copia fijada del runtime GUS ([`COMPOSE_M3_VENDOR.md`](COMPOSE_M3_VENDOR.md), gate §24). Decisión del usuario: vendoring fijado, sin submódulo y sin paquete todavía.
  - [x] **M3.3a** Inspeccionar iSyCode `main` actual: SHA, archivos C/headers mínimos, dependencias, flags, frontera con llama.cpp, qué es portable y qué es iOS o Android; qué NO se copia.
    - → Upstream: iSyCodeMovil `main` @ `9c8a659` (público, así que CI puede clonar sin token; ya incluye #6 anti-bucle, #7 y #8 `thinking_off`). **Subset mínimo = 3 archivos:** `Sources/Model/GUSLlamaBridge.c` (463 líneas) y `.h` (75): solo dependen de `<llama/llama.h>` + libc/pthread/stdatomic; chat template, neutralización de tokens de control, sampling y greedy son portables. Más `scripts/build-llama-xcframework.sh` (29 líneas), portable, que fija llama.cpp `842b188`, el pin que el bridge espera. **No se copian:** `GUSSignalTrap.c` (diagnóstico de crash; §20 lo deja para otro milestone), `gus_jni.c` (los símbolos JNI están atados a `dev.iyscode.movil`, así que TamagotchIA escribe su propio glue), `LlamaCppInferenceEngine.swift`/UI/catálogo/descargas. Flags de Android: `GGML_OPENMP=OFF`, `GGML_NATIVE=OFF`, shim `<llama/llama.h>`, `-Wl,-z,max-page-size=16384`. Acoplamiento: ninguno, así que no hay stop condition.
  - [x] **M3.3b** Script de sync (`--from <SHA>` explícito, allowlist, falla ante un layout inesperado, nunca HEAD) + manifiesto de provenance (repo, SHA, fecha, rutas, sha256).
    - → `tools/sync-gus-runtime.mjs` (Node, el toolchain del repo):
    - `--from <SHA de 40 hex>` obligatorio; rechaza `HEAD`, ramas y SHAs cortos;
    - lee de objetos git **en ese commit** (no del working tree), clonando el repo público o con `--source`;
    - copia solo la allowlist de 3 archivos, byte a byte;
    - falla si falta un archivo o si el bridge agrega un `#include` local nuevo;
    - escribe solo dentro de `vendor/gus-runtime`, con `VENDOR.json` (repo, commit, synced_at, pin de llama.cpp, sha256 por archivo).
    Modos: `--verify` (offline, compara contra el manifiesto) y `--check` (regenera el pin en temp y compara byte a byte). Probado contra el upstream real: `--check` por red en unos 2 s. Commit `1893ee6`.
  - [x] **M3.3c** Snapshot vendorizado y committeado, marcado como GENERATED, sin ediciones a mano.
    - → `vendor/gus-runtime/` generado con `--from 9c8a659840045cb31da7b501022645a194f4422d`: `Sources/Model/GUSLlamaBridge.c` (sha256 `b79fb3e4…`), `.h` (`c521205b…`), `scripts/build-llama-xcframework.sh` (`134f1d07…`, llama.cpp `842b188`) + `VENDOR.json` + README de GENERATED y de cómo mover el pin. Marcado `linguist-generated` en `.gitattributes`. `cmp` contra el upstream: idéntico. Sin ediciones a mano. Commit `08cca20`.
  - [x] **M3.3d** Tests del sync con un repo git fixture: SHA explícito, allowlist, determinismo, detecta drift y ediciones a mano, falla ante un layout inesperado, hashes.
    - → `tests/vendor.test.mjs` (9 tests, repos git reales en temp, sin red ni mocks de git):
    - solo acepta un SHA completo;
    - copia solo la allowlist, byte a byte, con hashes que coinciden;
    - es determinista;
    - lee el commit fijado aunque el upstream avance;
    - detecta una edición a mano, offline (`verify`) y contra el upstream (`check`);
    - detecta un manifiesto maquillado y archivos extra;
    - falla si un archivo se movió o si aparece un `#include` nuevo;
    - solo toca su directorio;
    - el snapshot committeado coincide con su manifiesto (corre en cada `npm test`).
    Vitest ahora también incluye `*.test.mjs`. Suite 108/108, tsc limpio. Commit `a2bceb5`.
  - [ ] **M3.3e** CI de drift: clona el upstream en el pin, regenera en temp y compara.
  - [ ] **M3.3f** Nota/ADR: por qué no submódulo, criterio para extraer un paquete después, y proceso para actualizar el pin.
- [ ] **M3.4** Runtime nativo conectado (gate §25). En dispositivo real: NOT_DEMONSTRATED hasta que haya prueba física.
  - [ ] **M3.4a** Smoke de escritorio: el bridge vendorizado + llama.cpp fijado + un modelo pequeño con hash congelado + ContextBox real → texto no vacío, UTF-8 válido, sin fugas de tokens de control, limpieza OK.
  - [ ] **M3.4b** Android: plugin Capacitor `GusLocal` (Kotlin) + glue JNI propio de TamagotchIA (bytes UTF-8) + CMake con el vendor; compila en CI.
  - [ ] **M3.4c** iOS: plugin Capacitor `GusLocal` (Swift) + xcframework de llama.cpp fijado; compila en CI.
  - [ ] **M3.4d** Tests del adapter: plugin ausente, error nativo, timeout, respuesta malformada o vacía, UTF-8, caja rechazada → fallback sin tocar el save.
  - [ ] **M3.4e** Provenance de cierre (§28): SHAs, rutas, hashes, tests, builds, evidencia de dispositivo y los huecos NOT_DEMONSTRATED.
- [ ] **M3.5** PWA: mensaje "GUS local requiere la app nativa" y el juego sigue funcionando.
- [ ] **M3.6** Prueba en teléfono físico con modo avión. Hasta entonces: NOT_DEMONSTRATED.

## M4 — Salida estructurada

- [ ] **M4.1** Probar la grammar de llama.cpp contra MindReplyV1 en el smoke de CI del catálogo.
- [ ] **M4.2** Validar el schema después de generar; lo inválido cae al fallback.
- [ ] **M4.3** Si la grammar no es fiable o portable, GUS genera solo `speech` y el código decide emoción, intención y animación.

## M5 — Interaction Gate

- [ ] **M5.1** Clases de datos: PET_CANON_STATE, PET_LIFE_LOG, PET_MEMORY, PET_RELATIONSHIPS, USER_CONVERSATION, USER_PRIVATE_CONTEXT, DEVICE_METADATA, SECRETS.
- [ ] **M5.2** Context Gate (qué se lee) separado del Contribution Gate (qué sale; apagado por defecto).
- [ ] **M5.3** Presets: Privado, Mascota solamente, Investigación, Personalizado.
- [ ] **M5.4** Remote Block Total, con un test que demuestre cero tráfico remoto.
- [ ] **M5.5** Fail closed: si la política no se puede leer, no hay egress.

## M6 — GUS remoto

- [ ] **M6.1** NVIDIA / NVAPI / Nebius detrás del mismo `GUSProvider`, recibiendo solo la proyección que permita el gate.
- [ ] **M6.2** Test local → remoto → local: misma criatura, mismos recuerdos.

## M7 — Local / Canon

- [ ] **M7.1** Las criaturas Canon nacen Canon; en Canon el modo dev está desactivado.
- [ ] **M7.2** "Crear copia de laboratorio": un fork a Local con `forked_from_canon_hash`.
- [ ] **M7.3** Tests: Local nunca recupera la elegibilidad Canon, y el modo dev no toca Canon.

## M8 — Recibos y LifeLog

- [ ] **M8.1** Hash de estado e historia con la criptografía del sistema (WebCrypto en TS).
- [ ] **M8.2** Replay determinista donde aplique: estado inicial + ruleset + semilla + acciones = estado final.
- [ ] **M8.3** Documentar el límite: esto es "válido según el protocolo", no anti-cheat.

## M9 — Vertical ISyMotron (Superficie B)

- [ ] **M9.1** Inspeccionar el Reviver existente en Munder (solo lectura, con permiso explícito del usuario).
- [ ] **M9.2** Inspeccionar la superficie de agente de ISyCode; no asumir que existe `isycode --agent`.
- [ ] **M9.3** Una capacidad real: Broker → Reviver → worker local → ISyCode / Authority → efecto → recibo.

## M10 — Demo del hackathon

- [ ] **M10.1** Superficie A: la misma criatura con cerebro local y remoto, Context Box, gate, cambio de modelo sin perder identidad y Remote Block.
- [ ] **M10.2** Superficie B: la vertical de M9 con recibo.
- [ ] **M10.3** Benchmarks (TTFT, prefill, tok/s, RAM, térmica), video y matriz de evidencia.

## Horizonte (diseñar contratos, NO implementar ahora)

World, lease de autoridad, avatar/takeover, mundo social, PvP, compute tiers, collab nodes, sponsors, OmniHarness (`isymotron up`), MCP + OAuth, adaptive polling. Ver secciones 16–37 del Compose.

---

## Registro de provenance

| Fecha | Tarea | Repo @ base | Rama | Qué cambió | Verificación |
|---|---|---|---|---|---|
| 2026-09-30 | M3.3d | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | tests/vendor.test.mjs, vite.config.ts | vitest 108/108, tsc |
| 2026-09-30 | M3.3c | TamagotchIA @ `b7fe4b1`, iSyCodeMovil @ `9c8a659` | `claude/gus-life-m1` | vendor/gus-runtime/**, .gitattributes | --verify y --check (red) OK; cmp idéntico |
| 2026-09-30 | M3.3b | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | tools/sync-gus-runtime.mjs, .gitignore | sync/verify/check reales contra iSyCodeMovil 9c8a659 |
| 2026-09-30 | M3.3a | iSyCodeMovil @ `9c8a659` | — | nada (inspección) | grep de includes, CMakeLists.txt, build script, project.yml |
| 2026-09-30 | M3.2 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/persona/localMind.ts, nativeGus.ts, tests/localMind.test.ts | vitest 99/99, tsc, build |
| 2026-09-30 | M3.1 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/persona/mind.ts, providers.ts, tests/mind.test.ts | vitest 96/96, tsc |
| 2026-09-30 | M2.4 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | tests/compile.test.ts | vitest 92/92, tsc |
| 2026-09-30 | M2.3 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | (mismo commit) | test 'orders keys from stable to volatile' |
| 2026-09-30 | M2.2 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | (mismo commit) | tests: 'drops in priority order', 'keeps the most important memories longest' |
| 2026-09-30 | M2.1 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/persona/compile.ts | vitest 92/92, tsc |
| 2026-09-30 | M1.6 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | tests/fixture-v1.test.ts, tests/fixtures/save-v1.b7fe4b1.json, src/store/save.ts | vitest 84/84, tsc; crash reproducido en el clon v1 |
| 2026-09-30 | M1.5 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/engine/types.ts, world.ts, src/store/save.ts, tests/migration.test.ts | vitest 80/80, tsc, vite build |
| 2026-09-30 | M1.4 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/persona/contextBox.ts, tests/contextBox.test.ts, tests/fixtures/context-box.example.json | vitest 73/73, tsc |
| 2026-09-30 | M1.3 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/persona/budget.ts, tests/budget.test.ts | vitest 69/69, tsc |
| 2026-09-30 | M1.2 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/life/lifelog.ts, src/engine/rules.ts (constante), tests/life.test.ts | vitest 64/64, tsc |
| 2026-09-30 | M1.1 | TamagotchIA @ `b7fe4b1` | `claude/gus-life-m1` | src/life/identity.ts, tests/life.test.ts | vitest 61/61, tsc |
| 2026-09-30 | M0.11 | IsyMotron | `claude/exciting-lamport-84gclk` | revisión del Gate contra COMPOSE §38/§40 |
| 2026-09-30 | M0.10 | IsyMotron | `claude/exciting-lamport-84gclk` | `docs/tamagotchia/M0_INSPECTION.md` \| vitest temporal para medir (borrado; el clon quedó limpio) |
| 2026-09-30 | M0.9 | TamagotchIA @ `b7fe4b1`, iSyCodeMovil @ `f6bda93` | — | nada (inspección) | comparación con life-packet/ y COMPOSE.md; grep en SPEC/ROADMAP/README/GUIA |
| 2026-09-30 | M0.8 | iSyCodeMovil @ `f6bda93` | — | nada (inspección) | include/llama.h @ 842b188; GUSLlamaBridge.c:224 en iSyCodeMovil main |
| 2026-09-30 | M0.7 | llama.cpp @ `842b188` | — | nada (inspección) | include/llama.h, src/CMakeLists.txt y nm de libllama.a en llama.cpp @ 842b188 |
| 2026-09-30 | M0.6 | iSyCodeMovil @ `f6bda93` | — | nada (inspección) | git show origin/main en iSyCodeMovil |
| 2026-09-30 | M0.5 | TamagotchIA @ `b7fe4b1` | — | nada (inspección) | lectura de persona/*.ts, engine/memory.ts, tests/persona.test.ts |
| 2026-09-30 | M0.4 | TamagotchIA @ `b7fe4b1` | — | nada (inspección) | lectura de store/save.ts, engine/world.ts, rules.ts, tests/store.test.ts |
| 2026-09-30 | M0.3 | TamagotchIA @ `b7fe4b1` | — | nada (inspección) | lectura de src/, capacitor.config.ts, app.ts |
| 2026-09-30 | M0.2 | TamagotchIA @ `b7fe4b1` | — | nada | vitest 58/58, tsc, vite build (Linux, Node 22) |
| 2026-09-30 | M0.1 | TamagotchIA @ `b7fe4b1` | — (solo lectura) | nada (inspección) | `git log -1` en el clon |
| 2026-09-30 | H1, H2 | IsyMotron @ `29344d0` | `claude/exciting-lamport-84gclk` | `docs/tamagotchia/` (COMPOSE, life-packet, ROADMAP) | Checksums del MANIFEST del paquete verificados; solo docs |
