# IsyMotron Móvil — roadmap vivo

> Handoff para cualquier agente: lee "Cómo retomar", haz la primera casilla sin tachar, tacha, commit y push.
> Decidido con el dueño el 2026-10-01: **IsyMotron Móvil es una app nueva, desde cero, en `mobile/`**.
> TamagotchIA se queda como está en su repo (su `main` no se toca) y más adelante se conecta como una función.
> Cuando las dos estén bien establecidas, se juntan en una sola app donde TamagotchIA es una feature.

## Cómo retomar

1. Lee este archivo completo y las reglas de abajo.
2. Repo `DannyBaanks/IsyMotron`, rama de trabajo `claude/exciting-lamport-84gclk` (la rama por defecto es `master`).
3. La app vive en `mobile/` (Capacitor 8 + Vite + TypeScript, igual que TamagotchIA). El núcleo Python no depende de ella.
4. Cada casilla termina con: tests verdes, commit pequeño, push, casilla tachada con una nota `→` de evidencia y una fila en el registro.
5. "Compila en CI" no es "funciona en el teléfono". Lo que no se probó en hardware queda **NOT_DEMONSTRATED**.

## Decisiones del dueño (2026-10-01)

| Pregunta | Decisión |
|---|---|
| Tecnología | Capacitor + TypeScript (una base para iPhone y Android; reutiliza lo aprendido en TamagotchIA) |
| Dónde | Carpeta `mobile/` dentro de IsyMotron; el IPA y el APK salen en las Actions de IsyMotron |
| Versión 1 | **Enlazar con tu PC**: emparejar con código de 6 dígitos (Link), ver el estado y mandar tareas |
| TamagotchIA | **Ver y actuar con permiso**: IsyMotron pide, TamagotchIA decide y deja recibo (milestone posterior) |

## Reglas que no se rompen

- El modelo propone, la autoridad local decide y queda un recibo. **El teléfono no es autoridad de la PC**: lo que el teléfono hace en la PC pasa por el Link sellado y lo decide la PC.
- Cripto de la app: **solo la de la plataforma** (WebCrypto: Ed25519, X25519, HKDF, AES-GCM). Nada hecho a mano en el teléfono.
- Llaves privadas: no extraíbles, nunca en logs, nunca en un export, nunca a un modelo.
- Un modelo remoto nunca recibe llaves, recibos completos ni el contenido de las tareas sin que el usuario lo elija.
- Emparejar solo con un código que el humano ve en las dos pantallas.
- No reescribir historia ni attestations de releases existentes.

## M0 — Inspección (sin tocar código)

- [x] **M0.1** Entender el Link de la PC (`core/isymotron/link/`, `tools/link_cli.py`).
  - → Identidad: Ed25519 (firma) + X25519 (cifrado); `office_id` = primeros 16 hex del SHA-256 de la llave pública de firma; base64url sin padding.
  - → Emparejar: `POST /link/v1/pair` con la tarjeta pública + `nonce` → la PC responde con su tarjeta + su `nonce`; ambos calculan el código `SHA-256("isymotron-link@1"|llaves ordenadas|nonces ordenados)` → 4 bytes big-endian mod 10⁶. La PC lo guarda como pendiente 10 min; el humano corre `isymotron link aceptar <código>`.
  - → Llamadas: `POST /link/v1/call {env}`; sobre `{v,from,to,ts,nonce,iv,ct,sig}`. Llave = HKDF-SHA256(X25519, salt = office_ids ordenados unidos por `|`, info `"isymotron-link@1 seal"`, 16 bytes) → AES-128-GCM con AAD `"from>to"`; firma Ed25519 sobre `"v|from|to|ts|nonce|iv|ct"`. Ventana de ±120 s y anti-replay de nonces.
  - → Operaciones de hoy: `ping`, `delegate` (deja la tarea en el inbox de la PC), `message`, `cancel`, `task` (estado). Recibos `link_received` del lado de la PC.
- [x] **M0.2** Huecos para el teléfono.
  - → **La PC solo escucha en `127.0.0.1`** (`LinkServer(host="127.0.0.1")`, sin opción en `link servir`): el teléfono no la alcanza. Hace falta un modo explícito "en mi red" (M3).
  - → El teléfono no es servidor: la PC no puede llamarlo. La v1 va en una dirección (teléfono → PC).
  - → El Link usa HTTP sin TLS en la red local. Los sobres van firmados y cifrados y el emparejamiento está protegido por el código; aun así, iOS (ATS) y Android (cleartext) lo bloquean por defecto. Hay que permitir solo la red local.
  - → **Hallazgo:** el lado PC del Link implementa Ed25519, X25519, AES y GCM en Python puro (`curve.py`, `aesgcm.py`), con vectores RFC. Choca con la regla "no implementar primitivas criptográficas de producción desde cero". Es previo a este trabajo y no se toca aquí. El teléfono usa la cripto de la plataforma y los tests de interoperabilidad (M2) contrastan las dos implementaciones byte a byte. Decisión del dueño pendiente.
  - → WebCrypto con Ed25519/X25519: iOS 17+ (WKWebView), Android System WebView 137+, Node 22 (para los tests). Si falta, la app lo dice y no empareja.

## M1 — Esqueleto de la app

- [x] **M1.1** `mobile/`: Capacitor 8 + Vite + TS, pantalla inicial en español, tests (vitest), `npm run build`.
  - → `mobile/` con Capacitor 8 + Vite + TS, appId `io.github.dannybaanks.isymotron`. Pantalla inicial en español: Mis PCs (enlazar llega en M4) y "Este teléfono", que prueba de verdad Ed25519, X25519, HKDF y AES-GCM de la plataforma; si falta uno, dice que no va a emparejar. Proyectos Android e iOS generados por Capacitor. vitest 3/3, tsc, build; se renderizó headless sin errores. Commit `5d62290`.
- [x] **M1.2** Workflow `mobile.yml`: tests + build + **APK** (Android) + **IPA sin firmar** (iOS) como artefactos en cada push que toque `mobile/` y en cada PR. Sin releases.
  - → `.github/workflows/mobile.yml`: tests + build → **IsyMotron-android-apk** (debug) e **IsyMotron-unsigned-ipa** como artefactos (30 días) en cada push que toque `mobile/` y en cada PR. Sin releases. Primer [run 36821707684](https://github.com/DannyBaanks/IsyMotron/actions/runs/36821707684) verde: tests, APK e IPA. **En teléfono: NOT_DEMONSTRATED.**

## M2 — Cliente Link en TypeScript (cripto de la plataforma)

- [x] **M2.1** Identidad con WebCrypto (llaves no extraíbles guardadas en IndexedDB), tarjeta pública, `office_id`, código de 6 dígitos.
  - → `mobile/src/link/identity.ts` + `keystore.ts`: Ed25519 + X25519 con WebCrypto y llaves privadas **no extraíbles**, guardadas en IndexedDB como objetos CryptoKey (nunca sus bytes). Se crea una vez y luego siempre es el mismo `office_id`. `office_id`, tarjeta pública y código de 6 dígitos iguales a los de la PC (vectores). Verificado en Chromium headless: IndexedDB guarda la llave no extraíble y sigue firmando. Commit `2a5d0ab`.
- [x] **M2.2** Sellar y abrir sobres idénticos al Python (vectores fijos generados por el Python de la PC; los mismos bytes en los dos sentidos).
  - → `envelope.ts` sella **byte a byte igual** que `core/isymotron/link/envelope.py` para las mismas llaves y la misma aleatoriedad, y abre lo que sella la PC. Al abrir rechaza remitente desconocido, destinatario equivocado, sobre alterado, hora vieja y replay. `mobile/tools/link_vectors.py` corre el código de la PC con llaves de prueba fijas; CI regenera los vectores y falla si cualquiera de los dos lados cambia. Commit `2a5d0ab`.
- [x] **M2.3** Prueba viva en CI: servidor Link real en Python + cliente TS en Node → emparejar, `link aceptar`, `ping`, `delegate`, `task`.
  - → Prueba viva: el servidor Link **real** de la PC (Python) en un puerto efímero + el cliente TS por HTTP real. Recorrido: emparejar → una llamada antes de aceptar se rechaza → la PC acepta el código → `ping` → `delegate` cae en el inbox de la PC con recibo `link_received` → `task` → `cancel`. Un código equivocado no empareja nada. **Hallazgo:** la PC contesta las llamadas en JSON sin sellar (la petición va sellada, la respuesta no). El teléfono muestra las respuestas pero nunca las trata como autoridad; queda como M3.2. Commit `12d6fe1`, CI [run 36822054916](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822054916) verde.

## M3 — La PC acepta al teléfono

- [x] **M3.1** `isymotron link servir --red`: escucha en la red local solo si el usuario lo pide, muestra la IP:puerto para escribirla en el teléfono y lo deja en un recibo. Por defecto sigue en `127.0.0.1`.
  - → `isymotron link servir --red` escucha en `0.0.0.0` **solo si el humano lo pide**. Imprime "En el teléfono escribe: IP:puerto" y el siguiente paso (`isymotron link aceptar <código>`), y deja el recibo `link_serve_lan`. Por defecto sigue en `127.0.0.1`. Tests: sin `--red` escucha en loopback y no deja recibo; con `--red` escucha en 0.0.0.0, responde `/link/v1/status`, imprime la dirección y escribe el recibo. pytest: 530 ok, 17 skipped (`test_linux_real::test_app_allowlist_runs_only_the_granted_file` falla en este sandbox con o sin el cambio). Commit `f1f1b25`.

- [x] **M3.2** Respuestas selladas: la PC también sella sus respuestas (campo extra, compatible con el CLI actual) y el teléfono solo confía en una respuesta firmada por la PC emparejada. Sin esto, alguien en la misma red podría fingir un "pong" mientras se empareja.
  - → **La PC** (`core/isymotron/link/server.py`) sigue respondiendo los mismos campos en claro, así que el CLI entre PCs sigue igual, y agrega `renv`: el resultado sellado de vuelta al que llama y atado al nonce de su petición (`re`). **El teléfono** solo cree una respuesta si `renv` abre con la llave de la PC emparejada, viene sellado para este teléfono, no es un replay y contesta a esta petición; el JSON en claro se ignora. Si la PC no sella, le pide actualizar. Tests: pytest con ida y vuelta de `renv` (una tercera oficina no lo puede abrir); prueba viva donde un "pong" falso en claro y uno sellado con la llave de un atacante se rechazan y el de la PC real pasa. pytest 531 ok; vitest 14/14; CI [run 36822646078](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822646078) verde. Commit `0e582df`.

## M4 — Pantallas de la v1

- [x] **M4.1** Enlazar: escribir IP:puerto de la PC → ver el código → confirmar que coincide → la PC queda guardada.
  - → Pantalla **Enlazar**: escribes la IP:puerto que da `isymotron link servir --red`. El teléfono muestra el nombre y la huella de la PC, el código grande (`187 327`) y el comando exacto `isymotron link aceptar <código>`. "Ya lo escribí" solo guarda la PC si vuelve una respuesta **sellada por esa PC**; antes de que la PC acepte dice "Tu PC no aceptó la petición". iOS: `NSAllowsLocalNetworking` + texto de red local, e internet sigue solo con HTTPS. Android: `network_security_config` con cleartext, porque no se puede limitar a rangos privados y las llamadas van selladas. **e2e en CI** (`mobile/e2e/pairing.e2e.mjs`, [run 36822953911](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822953911)): la app construida en Chromium, con botones reales, contra el servidor Link real de la PC. Commit `2194af0`. **Teléfono + PC reales en la misma Wi-Fi: NOT_DEMONSTRATED** (M4.3).
- [x] **M4.2** Mis PCs: estado (`ping`), mandar una tarea, seguirla (`task`), cancelar; recibos locales en el teléfono.
  - → Pantalla **Mi PC**: probar conexión (ping con respuesta firmada), mandar una tarea (título + detalles), ver su estado, cancelarla y olvidar la PC. Recibos del teléfono: `link_paired`, `link_delegated`, `link_cancelled`, `link_forgotten` (máx. 200). Las PCs se guardan como datos públicos en localStorage y las llaves siguen en IndexedDB. El e2e comprueba que la tarea cae en el inbox de la PC con su texto (🐱 incluido), pasa de `queued` a `cancelled` y la PC sigue enlazada después de recargar. CI [run 36822953911](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822953911) verde (tests, e2e, APK e IPA).
- [x] **M4.4** Rediseño "Verde terminal" con Malbolgato v2 en Inicio (pedido del dueño, 2026-10-01): atlas Codex de Companion `main`, gestos (tocar, doble toque, arrastrar, mantener, mirada), conectado al Link real, marco de autoridad solo con respuestas selladas, pestañas Inicio/Tareas/Recibos/Teléfono.
  - → Toda la app quedó en **Verde terminal**, con Malbolgato v2 en Inicio. Usa el atlas Codex y la hoja de cargar de Companion `main` @ `ffa2b13`, a 0.75 en WebP, dentro de `mobile/public/malbolgato`. `src/pet.ts` usa las mismas filas y tiempos que la ventana GTK de Companion. Gestos: tocar = saluda, doble toque = salta, arrastrar = lo cargas y aterriza, mantener = controles (ping, mandar tarea, enlazar, jugar), tocar la tarjeta = te mira. Sigue a la app real: revisa al preguntar, trabaja al delegar, espera al enlazar, saluda con una respuesta sellada y pone cara de falló con un error. **No tiene autoridad.** El marco de autoridad solo muestra respuestas selladas por la PC y se apaga a los 8 s. Pestañas: Inicio, Tareas, Recibos, Teléfono. Fuentes empaquetadas para usarse sin internet. El e2e en CI suma: Malbolgato dibujado desde el atlas, el menú al mantenerlo presionado y las 4 pestañas sin errores. Se corrigió en el camino un marco de autoridad que salía vacío. vitest 22/22; CI [run 36838884718](https://github.com/DannyBaanks/IsyMotron/actions/runs/36838884718) verde (tests, e2e, APK, IPA). Commit `19763f0`. **En iPhone: visto funcionando (captura del dueño, 2026-10-01)**: Inicio Verde terminal con Malbolgato v2, usado en la misma prueba real de M4.3 (enlace y tarea con respuesta sellada). Sin evidencia todavía, así que siguen NOT_DEMONSTRATED: cada gesto por separado en el teléfono (arrastrar, doble toque, mirada, jugar, menú) y **Android**.
- [x] **M4.3** Prueba física: teléfono + PC en la misma Wi-Fi. Hasta entonces: NOT_DEMONSTRATED.
  - → **Demostrado por el dueño (2026-10-01)**, iPhone real + PC Linux en la misma Wi-Fi, app en `c752466` (Verde terminal con Malbolgato v2). PC: `isymotron link servir --red` → recibo `link_serve_lan` (`192.168.1.102:47931`). Teléfono: Enlazar → código `948877` → en la PC `isymotron link aceptar 948877` → "enlazada con isytron-telefono". "Ya lo escribí" guardó `isytron-dannyisyco` (huella `f9f8 cdad`) en Mis PCs, es decir, volvió una respuesta sellada por esa PC. Tarea desde el teléfono → recibo `link_received` en la PC (`2026-10-01T12:46:50Z`, `task-1790858810364-ed03`, `from 7b92cc42df6f99d2`) e inbox con 1 en cola.

## M5 — Permisos desde el teléfono

- [x] **M5.1** Nuevas operaciones del Link para ver los permisos (leases) pendientes de la PC y responder sí/no. La PC decide y deja recibo; el teléfono solo es el dedo del humano.
  - → Agente local crea solicitudes por loopback; el teléfono emparejado solo las lista y responde mediante operaciones Link firmadas/cifradas. El `Host` de la PC aplica grant, alcance y TTL máximos; una aprobación humana no puede conceder permisos ausentes. La lease utilizable se entrega solo al agente local, nunca al teléfono. Recibos quedan en PC y teléfono. Evidencia local: pytest 544 passed / 15 skipped (3 fallos ajenos al menú PTY), Vitest 27/27, build + e2e Chromium verdes. Aprobación real desde la app enlazada demostrada el 2026-10-01: solicitud `permission-0815426a03f14653952a825da9e14f4b`, recibo PC `2026-10-01T21:48:00Z`; lease de 60 s con `scope: {}`. La aprobación funciona; la concesión de acceso de escritura sigue sin demostrarse porque el grant local no tiene alcance.

## M6 — GUS en el teléfono

- [x] **M6.1** Chat con GUS local y remoto solo si el usuario lo elige.
  - → Implementado y empaquetado en **v1.2.0-rc.2**: GUS local con catálogo GGUF fijado y verificación de tamaño/SHA-256, importación/exportación mediante el selector del sistema, NVIDIA Nemotron 3 Nano como opción local experimental y proveedor remoto explícito con preset NVIDIA NIM. El modo remoto no hace fallback automático ni recibe datos de Link, permisos o archivos de las PCs. APK e IPA se construyen en CI. **Inferencia física local en teléfonos sigue NOT_DEMONSTRATED** hasta medir rendimiento, memoria, temperatura y batería on-device. Ver [GUS_GUIDE.md](GUS_GUIDE.md).

## M7 — TamagotchIA como función

- [ ] **M7.1** Ver a la criatura: estado, recuerdos (solo lectura).
- [ ] **M7.2** Actuar con permiso: IsyMotron pide (darle de comer, jugar), el motor de TamagotchIA decide y deja recibo.

## M8 — Una sola app

- [ ] **M8.1** Juntar IsyMotron Móvil y TamagotchIA en una app; TamagotchIA queda como una feature.

## Registro de provenance

| Fecha | Tarea | Repo @ base | Rama | Qué cambió | Verificación |
|---|---|---|---|---|---|
| 2026-10-01 | M5.1 | IsyMotron @ `e9228e5` | `claude/exciting-lamport-84gclk` | core/isymotron/link/{permissions,server}.py, tools/link_cli.py, tests/test_link_{permissions,server,identity}.py, docs/LINK.md, mobile/src/{home,link/client,store,styles}.ts/css, mobile/tests/live.test.ts, mobile/tools/link_pc_for_tests.py, mobile/e2e/pairing.e2e.mjs | pytest 544 passed / 15 skipped; 3 PTY menu failures unrelated; Vitest 27/27; CI build + Chromium e2e + APK + IPA pass; app approval demonstrated (`permission-0815426a03f14653952a825da9e14f4b`, receipt `2026-10-01T21:48:00Z`); write access not demonstrated (`scope: {}`) |
| 2026-10-01 | M4.4 | IsyMotron @ `474bd3d`, Companion @ `ffa2b13` | `claude/exciting-lamport-84gclk` | mobile/src/{pet,home,main}.ts, mobile/src/styles.css, mobile/public/malbolgato/*, mobile/tests/pet.test.ts, mobile/e2e/pairing.e2e.mjs | vitest 22/22; e2e + APK + IPA en [run 36838884718](https://github.com/DannyBaanks/IsyMotron/actions/runs/36838884718) |
| 2026-10-01 | M4.2 | IsyMotron @ `0e582df` | `claude/exciting-lamport-84gclk` | mobile/src/home.ts, mobile/src/store.ts, mobile/tests/store.test.ts | vitest 17/17; e2e en [run 36822953911](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822953911) |
| 2026-10-01 | M4.1 | IsyMotron @ `0e582df` | `claude/exciting-lamport-84gclk` | mobile/src/home.ts, main.ts, store.ts, styles.css, Info.plist, AndroidManifest.xml, network_security_config.xml, e2e/pairing.e2e.mjs, mobile.yml | vitest 17/17; e2e en [run 36822953911](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822953911) |
| 2026-10-01 | M3.2 | IsyMotron @ `f1f1b25` | `claude/exciting-lamport-84gclk` | core/isymotron/link/server.py, tests/test_link_server.py, mobile/src/link/client.ts, mobile/tests/live.test.ts | pytest 531 passed; vitest 14/14; [run 36822646078](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822646078) success |
| 2026-10-01 | M3.1 | IsyMotron @ `12d6fe1` | `claude/exciting-lamport-84gclk` | tools/link_cli.py, tests/test_link_cli.py | pytest local 530 passed |
| 2026-10-01 | M2.3 | IsyMotron @ `2a5d0ab` | `claude/exciting-lamport-84gclk` | mobile/src/link/client.ts, mobile/tools/link_pc_for_tests.py, mobile/tests/live.test.ts | vitest 13/13 (live incluida); [run 36822054916](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822054916) success |
| 2026-10-01 | M2.2 | IsyMotron @ `18c49f3` | `claude/exciting-lamport-84gclk` | mobile/src/link/envelope.ts, mobile/tools/link_vectors.py, mobile/tests/fixtures/link-vectors.json, mobile.yml | vitest 10/10; drift de vectores en [run 36822054916](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822054916) |
| 2026-10-01 | M2.1 | IsyMotron @ `18c49f3` | `claude/exciting-lamport-84gclk` | mobile/src/link/{bytes,identity,keystore}.ts | vitest, vectores de la PC; [run 36822054916](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822054916) |
| 2026-10-01 | M1.2 | IsyMotron @ `22034d6` | `claude/exciting-lamport-84gclk` | .github/workflows/mobile.yml | GitHub Actions [run 36821707684](https://github.com/DannyBaanks/IsyMotron/actions/runs/36821707684) success |
| 2026-10-01 | M1.1 | IsyMotron @ `22034d6` | `claude/exciting-lamport-84gclk` | mobile/* | vitest 3/3, tsc, vite build, render headless |
| 2026-10-01 | M4.4 (teléfono) | IsyMotron @ `4aabe32` | `claude/exciting-lamport-84gclk` | solo roadmap | captura del dueño: Malbolgato en iPhone durante la prueba de M4.3 |
| 2026-10-01 | M0.1–M0.2 | IsyMotron @ `66f80bd` | `claude/exciting-lamport-84gclk` | solo lectura | inspección de `core/isymotron/link/*`, `tools/link_cli.py` |
