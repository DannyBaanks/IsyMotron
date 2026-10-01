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
- [ ] **M2.2** Sellar y abrir sobres idénticos al Python (vectores fijos generados por el Python de la PC; los mismos bytes en los dos sentidos).
- [ ] **M2.3** Prueba viva en CI: servidor Link real en Python + cliente TS en Node → emparejar, `link aceptar`, `ping`, `delegate`, `task`.

## M3 — La PC acepta al teléfono

- [ ] **M3.1** `isymotron link servir --red`: escucha en la red local solo si el usuario lo pide, muestra la IP:puerto para escribirla en el teléfono y lo deja en un recibo. Por defecto sigue en `127.0.0.1`.

## M4 — Pantallas de la v1

- [ ] **M4.1** Enlazar: escribir IP:puerto de la PC → ver el código → confirmar que coincide → la PC queda guardada.
- [ ] **M4.2** Mis PCs: estado (`ping`), mandar una tarea, seguirla (`task`), cancelar; recibos locales en el teléfono.
- [ ] **M4.3** Prueba física: teléfono + PC en la misma Wi-Fi. Hasta entonces: NOT_DEMONSTRATED.

## M5 — Permisos desde el teléfono

- [ ] **M5.1** Nuevas operaciones del Link para ver los permisos (leases) pendientes de la PC y responder sí/no. La PC decide y deja recibo; el teléfono solo es el dedo del humano.

## M6 — GUS en el teléfono

- [ ] **M6.1** Chat con GUS local (runtime vendorizado de iSyCode Móvil, como en la rama `claude/gus-life-m1` de TamagotchIA) y remoto solo si el usuario lo elige.

## M7 — TamagotchIA como función

- [ ] **M7.1** Ver a la criatura: estado, recuerdos (solo lectura).
- [ ] **M7.2** Actuar con permiso: IsyMotron pide (darle de comer, jugar), el motor de TamagotchIA decide y deja recibo.

## M8 — Una sola app

- [ ] **M8.1** Juntar IsyMotron Móvil y TamagotchIA en una app; TamagotchIA queda como una feature.

## Registro de provenance

| Fecha | Tarea | Repo @ base | Rama | Qué cambió | Verificación |
|---|---|---|---|---|---|
| 2026-10-01 | M2.1 | IsyMotron @ `18c49f3` | `claude/exciting-lamport-84gclk` | mobile/src/link/{bytes,identity,keystore}.ts | vitest, vectores de la PC; [run 36822054916](https://github.com/DannyBaanks/IsyMotron/actions/runs/36822054916) |
| 2026-10-01 | M1.2 | IsyMotron @ `22034d6` | `claude/exciting-lamport-84gclk` | .github/workflows/mobile.yml | GitHub Actions [run 36821707684](https://github.com/DannyBaanks/IsyMotron/actions/runs/36821707684) success |
| 2026-10-01 | M1.1 | IsyMotron @ `22034d6` | `claude/exciting-lamport-84gclk` | mobile/* | vitest 3/3, tsc, vite build, render headless |
| 2026-10-01 | M0.1–M0.2 | IsyMotron @ `66f80bd` | `claude/exciting-lamport-84gclk` | solo lectura | inspección de `core/isymotron/link/*`, `tools/link_cli.py` |
