# Auditoría de las actualizaciones de IsyMotron

Fecha: 21 de octubre de 2026, America/Mexico_City.

**Resultado: los builds y las pruebas existentes pasan, pero hay problemas de integración, representación de evidencia y recuperación de GUS que conviene corregir antes de dar la actualización por terminada.** Se confirmó además una exposición de datos preexistente en el proxy web.

## Versiones y alcance

Se consultó GitHub y se descargaron referencias sin cambiar la rama ni los archivos del producto en el checkout del usuario. La copia local estaba en `claude/exciting-lamport-84gclk`, commit `c0bf8d5`, anterior a estas actualizaciones. Las pruebas se ejecutaron en snapshots separados:

| Superficie | Revisión auditada | Contenido |
|---|---|---|
| Principal y web | `98648b3b647b8110b89b5984dd1e355e816530ff` | `origin/master`: launcher móvil inicial, nuevo panel web, documentación |
| Móvil más reciente | `26b023daead6478d08a0eb75b2bac43ae3dc6c58` | `origin/feature/isymotron-performance-1`: interacciones, GUS diferido, atlas diferido y corrección del generador |
| Base de comparación | `fac3177` | Última integración anterior a los cambios del 20 de octubre |

Los commits se compararon y se probaron sus interfaces. No se atribuye autoría a un modelo concreto: Git identifica al autor de los commits, no cuál de los modelos de Manus los produjo.

## Hallazgos

### 1. [P1] El proxy web entrega estado protegido sin autenticar al visitante — preexistente

Código: [web/app/api/dashboard/route.ts, líneas 3–18](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/app/api/dashboard/route.ts#L3-L18).

Cuando `ISYMOTRON_SESSION_TOKEN` está configurado, cualquier cliente que alcance `/api/dashboard` recibe el estado del backend. La ruta utiliza la credencial del servidor sin comprobar cookie, token o identidad del visitante y reenvía el JSON completo, incluyendo resultados de operaciones, parámetros y scopes. Ocultar el token del navegador no autentica al navegador.

**Reproducción local:** backend de prueba con credencial sintética y un resultado privado ficticio. Consulta directa sin token: **401**. Consulta al proxy Next sin token ni cookie: **200**, incluyendo el resultado privado. Evidencia: [auth-results.json](evidence/auth-results.json), [reproductor](repro/auth_audit.py).

**Impacto:** divulgación de datos si el frontend es accesible por terceros y tiene acceso a un backend real. La exposición remota depende de cómo se publique el frontend; no se inspeccionó un despliegue público. Esta ruta no concede ejecución por sí misma.

**Corrección:** autenticar al visitante antes de utilizar la credencial del backend y devolver un DTO de solo lectura con los campos necesarios. Corregir también la afirmación de `docs/GUS_WEB_ENDPOINT.md` de que ya existe una sesión web protegida: la implementación auditada no la tiene.

### 2. [P1] El flujo afirma que una acción quedó sellada aunque el sello sea inválido — nuevo panel web

Código: [web/app/page.tsx, línea 132](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/app/page.tsx#L132).

La leyenda usa solamente `latestReceipt.decision === "ALLOW"` para mostrar «La última decisión fue permitida y quedó sellada». Los pasos de ejecución y registro también se completan por decisión o existencia del receipt, sin exigir verificación.

**Reproducción:** respuesta compatible con el contrato, `decision: ALLOW` y `seal_ok: false`. El resumen muestra **«Todo en orden … quedó sellada»** mientras la tabla muestra **«Pendiente»**. Evidencia: `badseal_caption` en [browser-results.json](evidence/browser-results.json) y [captura](evidence/web-invalid-seal.png).

**Impacto:** el canal visual afirma evidencia que el propio backend no confirmó. Es un error de representación, no una ampliación de permisos del host.

**Corrección:** representar autorización, resultado de ejecución y verificación de sello por separado; nunca deducir ejecución o sello de `ALLOW`.

### 3. [P2] Tres PR aparecen fusionados, pero sus mejoras móviles no están en master

El historial de GitHub confirma esta cadena de bases:

| PR | Rama destino de la fusión |
|---|---|
| [#6: launcher móvil](https://github.com/DannyBaanks/IsyMotron/pull/6) | `master` |
| [#7: interacciones y estados](https://github.com/DannyBaanks/IsyMotron/pull/7) | `feature/malbolgato-floating-chat` |
| [#9: rendimiento y GUS diferido](https://github.com/DannyBaanks/IsyMotron/pull/9) | `feature/isymotron-premium-interactions` |
| [#11: atlas y generador](https://github.com/DannyBaanks/IsyMotron/pull/11) | `feature/isymotron-performance-1` |

Las fusiones #7, #9 y #11 ocurrieron después de que sus ramas destino hubieran sido fusionadas en el nivel anterior. Esas fusiones anteriores no se actualizan retroactivamente.

**Verificación:** `git merge-base --is-ancestor <commit> origin/master` devuelve falso para `395d7f8`, `2fec334`, `98c0b74` y `fa4470f`. Frente al ancestro común, la rama móvil tiene 10 archivos de cambios pendientes de integración.

**Impacto:** compilar o publicar desde `master` no incluye las últimas mejoras de la app aunque los PR indiquen `MERGED`.

**Corrección:** preparar una integración final hacia `master` después de corregir los hallazgos móviles. No reemplazar `master` por la rama móvil: esta tampoco contiene los cambios independientes del panel web.

### 4. [P2] El contador de equipos activos no entiende la respuesta real del backend — nuevo panel web

Código: [web/app/page.tsx, línea 50](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/app/page.tsx#L50).

El contador exige `host.health.power_state` y `host.health.network_state`. `Host.health()` devuelve `ok`, `engine`, `contract`, contadores y `host_id`; los estados de energía/red están en el bloque de awareness.

**Reproducción:** snapshot generado por `ConsoleState`, `LoopbackRelay`, `ModernHost`, `LegacyHost` y `HostAwarenessEngine`, sin inventar el contrato. La pantalla muestra simultáneamente **«0 activos»** y **«Victus … listo para trabajar»**. Evidencia: `real_backend_summary` en [browser-results.json](evidence/browser-results.json), [captura](evidence/web-real-contract.png).

**Corrección:** adaptar los campos existentes y distinguir salud, disponibilidad y energía por host. No inferir el estado de todos los hosts a partir del awareness de uno solo.

### 5. [P2] Los tiempos de actividad se inventan y la frescura no caduca — nuevo panel, con consulta única preexistente

Código: [web/lib/dashboard.js, línea 24](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/lib/dashboard.js#L24), [page.tsx, líneas 72–92](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/app/page.tsx#L72-L92) y [línea 137](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/app/page.tsx#L137).

El backend ya devuelve `wall` como timestamp de finalización, pero el adaptador solo lee `observed_at`/`created_at`. La UI sustituye fechas ausentes por «Ahora», «14 s», «28 s» o múltiplos del índice. Además, `lastChecked` es un texto fijo y solo se consulta al montar o pulsar actualizar: «Conectado en vivo» y «Actualizado Ahora» pueden permanecer indefinidamente tras una desconexión.

**Reproducción:** un receipt con `wall: 1700000000` aparece como **«Ahora»**. El snapshot emitido por el backend real también pierde su `wall`. Evidencia: `real_backend_receipts` y `wrong_host_receipt` en [browser-results.json](evidence/browser-results.json).

**Corrección:** convertir `wall` de segundos a fecha, mostrar «fecha desconocida» cuando corresponda y calcular edad real del último chequeo. Implementar actualización periódica/eventos o presentar explícitamente una instantánea con su antigüedad.

### 6. [P2] Los recibos se atribuyen siempre al primer equipo — nueva tabla web

Código: [web/lib/dashboard.js, líneas 18–27](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/lib/dashboard.js#L18-L27) y [page.tsx, línea 137](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/app/page.tsx#L137).

El adaptador descarta `receipt.host` y cada fila recibe `snapshot.host.label`, que corresponde a `hosts[0]`.

**Reproducción:** fixture con dos hosts y receipt cuyo `host` es `win98-retrobox`: la tabla lo atribuye a **«Victus (Windows 11)»**. Evidencia: `wrong_host_receipt` en [browser-results.json](evidence/browser-results.json).

**Impacto:** una auditoría visual de varios equipos identifica incorrectamente dónde ocurrió la decisión.

**Corrección:** conservar `receipt.host` y resolver la identidad por ese identificador; si no existe, mostrar el identificador o un estado desconocido.

### 7. [P2] El catálogo oculta descripción y alcance que sí existen — nuevo catálogo web

Código: [web/app/page.tsx, línea 131](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/web/app/page.tsx#L131), [ConsoleState.snapshot](https://github.com/DannyBaanks/IsyMotron/blob/98648b3b647b8110b89b5984dd1e355e816530ff/console/server.py#L144-L173).

La tarjeta busca `capability.description` y `capability.scope`. El contrato expone `summary`, y el alcance concedido se publica en `host.scopes[capability.id]`. La vista muestra «Descripción no disponible en el contrato actual» y «Alcance: No especificado» aunque existen.

**Reproducción:** `filesystem.read` con summary y roots `C:/Photos` publicados por `ConsoleState`; ambos desaparecen en la tarjeta. Evidencia: `real_backend_capability` en [browser-results.json](evidence/browser-results.json).

**Corrección:** adaptar el contrato real. Mostrar límites mediante la representación lógica de rutas del proyecto, sin trasladar rutas físicas sensibles directamente al frontend. El riesgo sí puede permanecer desconocido cuando el backend no lo publique.

### 8. [P2] Terminar la carga diferida de GUS revierte la navegación del usuario — rama móvil nueva

Código: [mobile/src/home.ts, líneas 426–432](https://github.com/DannyBaanks/IsyMotron/blob/26b023daead6478d08a0eb75b2bac43ae3dc6c58/mobile/src/home.ts#L426-L432).

`loadGus().then(() => gusScreen())` abre el chat al completar la descarga sin comprobar si sigue siendo la pantalla solicitada.

**Reproducción en Chromium:** retener el chunk de chat, abrir GUS, pulsar «‹ Inicio» y liberar la descarga. La app vuelve sola a GUS. Evidencia: `mobile_left_loading_screen` y `mobile_loading_forces_navigation_back_to_gus`, ambos true, en [browser-results.json](evidence/browser-results.json).

**Corrección:** usar un identificador de navegación/carga o invalidar el callback al abandonar esa pantalla.

### 9. [P2] Un error cargando GUS queda memorizado y bloquea reintentos — rama móvil nueva

Código: [mobile/src/home.ts, líneas 241–260](https://github.com/DannyBaanks/IsyMotron/blob/26b023daead6478d08a0eb75b2bac43ae3dc6c58/mobile/src/home.ts#L241-L260).

`gusLoad` conserva la promesa rechazada. Volver a entrar reutiliza ese rechazo sin intentar cargar de nuevo. Según la causa, también puede intervenir la caché de imports del navegador; limpiar solamente la promesa de aplicación puede no ser suficiente.

**Reproducción en Chromium:** abortar la primera petición del chunk, regresar a Inicio, restaurar la red y abrir GUS. El mismo error reaparece sin una nueva solicitud. Evidencia: `mobile_load_failure_persists_after_network_restored` y `mobile_chunk_requests_before_retry: 1` en [browser-results.json](evidence/browser-results.json).

**Corrección:** restablecer el estado tras error y proporcionar una recuperación explícita; contemplar recarga de la app cuando haya un chunk obsoleto o un import fallido cacheado.

## Verificación ejecutada

| Revisión | Prueba | Resultado |
|---|---|---|
| master `98648b3` | `python -m pytest -q -rs` | **544 pasan, 15 omitidas, 0 fallos**; 57.80 s |
| master `98648b3`, web | `npm test` | **3 pasan** |
| master `98648b3`, web | `npm run build` | **Pasa**; Next 15.5.26 instalado |
| móvil `26b023d` | `npm test` | **72 pasan, 16 archivos** |
| móvil `26b023d` | `npm run build` | **Pasa**; TypeScript, Vite y ausencia de mock E2E en producción |
| móvil `26b023d` | `npm run e2e` | **Pasa**: pairing real con servidor Python de prueba, tarea/cancelación, permisos, reload y launcher |
| móvil `26b023d` | `npm run e2e:gus` | **Pasa**: controles de modelos, límites, aislamiento local y petición remota explícita contra mocks |
| ambos | Reproductores adicionales en Chromium | **Confirman los fallos descritos** |

Se reutilizaron las dependencias instaladas localmente mediante enlaces desde los snapshots; no se ejecutó una instalación limpia. Las comprobaciones E2E de GUS utilizan el modo de pruebas y no prueban inferencia real en un teléfono.

Se inspeccionaron además ejecuciones de GitHub Actions: [CI de master](https://github.com/DannyBaanks/IsyMotron/actions/runs/39529128638) y [APK + IPA de la rama móvil](https://github.com/DannyBaanks/IsyMotron/actions/runs/39531398021) figuran exitosas. Ese estado no cubre los escenarios de carga fallida ni las discrepancias del panel web aquí reproducidas. `ci.yml` comprueba Python y binarios; `mobile.yml` comprueba `mobile/`. No se encontró una tarea que ejecute las pruebas/build de `web/` en esos workflows.

## Estado funcional y observaciones menores

- **Chat móvil:** el launcher sí abre GUS; el flujo normal pasa sus E2E.
- **Chat web:** es un panel informativo sin compositor ni endpoint de conversación. Está expresamente marcado como pendiente en la UI y en la documentación; no es una integración terminada de GUS.
- **Responsive:** a 390 × 844 no se observó desbordamiento horizontal en el panel web; se guardaron capturas de escritorio y móvil.
- **Accesibilidad:** Escape no cierra el drawer web; la preferencia de movimiento reducido desactiva CSS, pero el `<img>` sigue apuntando al GIF animado. Son pendientes menores frente a los hallazgos anteriores.
- **Autoridad:** los commits comparados no modifican el enforcer, grants, leases ni el protocolo Link. La suite Python pasa. Esto no demuestra funcionamiento nativo en dispositivos físicos.
- **No probado localmente:** ejecución de APK/IPA en teléfono, inferencia de modelos reales ni un despliegue público. Se consultó el resultado del CI nativo, no se ejecutaron builds nativos nuevos.

## Entrega y siguiente paso

Esta auditoría agrega solamente este informe, reproductores y evidencia; no corrige ni publica producto. Prioridad propuesta: proteger el proxy; corregir evidencia y adaptación del contrato web; reparar la carga de GUS; integrar la cadena móvil en `master` y comprobar esa combinación final.

Snapshots usados: `/tmp/isymotron-audit-20261021-9gqd5ba8/master` y `/tmp/isymotron-audit-20261021-9gqd5ba8/mobile`. Los reproductores conservan esas rutas para repetir la sesión mientras existan. La evidencia guardada en este directorio permanece independiente de esos temporales.
