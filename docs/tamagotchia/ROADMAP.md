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
| Código del juego (M1–M8) | `DannyBaanks/TamagotchIA` | se crea en M1 (`claude/…`) |
| Runtime GUS a reutilizar | `DannyBaanks/iSyCodeMovil` | `main` |
| Reviver (M9) | Munder | **solo lectura y solo si el usuario lo autoriza** |

## Estado actual

- **Milestone activo:** M0 (solo inspección, sin tocar código).
- **Bloqueo:** esta sesión aún no tiene acceso a `DannyBaanks/TamagotchIA`.
- **Pendiente externo:** iSyCodeMovil PR #8 (`/no_think`) espera que termine el smoke con el build portable.

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

- [ ] **M0.1** Acceso de lectura a `DannyBaanks/TamagotchIA`; registrar rama, HEAD y fecha.
- [ ] **M0.2** Correr los tests y el build actuales (`npm test` / `check` / `build` o equivalentes); registrar resultados reales.
- [ ] **M0.3** Mapear engine, persona, memory, store, providers, UI y Capacitor iOS/Android, con paths reales.
- [ ] **M0.4** Formato del save: versión, migraciones existentes y fixtures.
- [ ] **M0.5** Contrato de persona actual (`personaInput`, `PersonaReply`, prompt) contra MindReplyV1 del ZIP.
- [ ] **M0.6** Qué se reutiliza de iSyCode Móvil, verificado en `main`:
  - contexto: 2048 y 4096 soportados por `gus_llama_create`;
  - `ModelContextBudget` (PR #7);
  - sampling anti-bucle (PR #6);
  - `thinking_off` (PR #8);
  - texto UTF-8 como bytes en JNI;
  - catálogo + SHA-256 + import desde Archivos;
  - flight recorder.
- [ ] **M0.7** Grammar / constrained decoding en el commit fijado de llama.cpp: ¿existe `llama_sampler_init_grammar`? ¿Compila en iOS y Android? (se investiga, no se implementa).
- [ ] **M0.8** Reutilizar el prefijo (KV) en el bridge: hoy `generate` llama `llama_memory_clear` en cada respuesta. Documentar qué haría falta, sin hacks.
- [ ] **M0.9** Deltas: ZIP ↔ repo, ZIP ↔ Compose y documentos que quedaron viejos.
- [ ] **M0.10** Escribir `M0_INSPECTION.md`:
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
- [ ] **M0.11** Gate: si M0 contradice el Compose, detenerse y reportar. Si está limpio, seguir con el slice mínimo de M1.

## M1 — Contrato de datos (TamagotchIA, tests primero)

- [ ] **M1.1** `PetIdentity`: id estable, especie, rasgos iniciales, nacimiento. Sin ningún campo de modelo o proveedor.
- [ ] **M1.2** `LifeLog`: evento con provenance (fuente, timestamp, versión del ruleset); append-only.
- [ ] **M1.3** `ContextBudget`: `total − salida reservada − contrato del sistema − turno actual = contexto disponible para la mascota`.
- [ ] **M1.4** Schema `ContextBox` v1, versionado y alineado con `life-packet/schemas/`.
- [ ] **M1.5** Marcador `mode: local | canon` + `ruleset_version` en el save, con migración no destructiva.
- [ ] **M1.6** Fixtures del save anterior, test de migración, roundtrip y manejo de entradas corruptas.

## M2 — Context compiler

- [ ] **M2.1** Compilar el Context Box desde el estado, como función pura con reloj inyectado.
- [ ] **M2.2** Prioridades: contrato > identidad > estado actual > evento > recuerdos relevantes > relación > historia > detalles.
- [ ] **M2.3** Orden de lo estable a lo volátil, para poder reutilizar el prefijo más adelante.
- [ ] **M2.4** Tests:
  - nunca excede el presupuesto;
  - las prioridades son estables;
  - lo irrelevante se cae primero;
  - el estado actual siempre queda;
  - los secretos nunca entran;
  - misma entrada, misma salida.

## M3 — GUS local

- [ ] **M3.1** Interfaz `CreatureMind` / `GUSProvider` con implementaciones fallback, remoto existente y local (placeholder).
- [ ] **M3.2** Frontera del plugin Capacitor. Recibe solo strings/JSON del Context Box, nunca `World` mutable.
- [ ] **M3.3** iOS: reutilizar el bridge C y llama.cpp de iSyCode Móvil sin duplicar el catálogo.
- [ ] **M3.4** Android: reutilizar JNI, CMake y el motor Kotlin.
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
| 2026-09-30 | H1, H2 | IsyMotron @ `29344d0` | `claude/exciting-lamport-84gclk` | `docs/tamagotchia/` (COMPOSE, life-packet, ROADMAP) | Checksums del MANIFEST del paquete verificados; solo docs |
