# IsyMotron: roadmap de 9 días — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Ejecutar en la sesión actual; este documento no solicita delegación automática.

**Goal:** Entregar PC + app móvil utilizables en un iPhone 12, con GUS local pequeño, tareas explícitas bajo autoridad de la PC y un panel web con evidencia fiel, antes del cierre del 30 de octubre de 2026.

**Architecture:** Conservar Python como autoridad, Link como transporte sellado, GUS como orientación y Next como monitor autenticado. Integrar primero las ramas que hoy contienen partes distintas del producto. Corregir el contrato entre backend y panel y probar el recorrido completo sobre la misma revisión.

**Tech Stack:** Python estándar, pytest, Next.js/React, Node test runner, TypeScript/Vite/Vitest, Capacitor, Swift, llama.cpp fijado, Chromium/Playwright e iPhone 12 físico.

**Spec:** [Alcance y aceptación](../specs/2026-10-21-hackathon-release-design.md).

**Actualización de procedencia:** GUS ya respondió offline en el iPhone mediante iSyCodeMovil, según el usuario. El caso «Don Zelaya» (`bea62f4`, Qwen1.5 1.8B) está en el historial de ese repo; IsyMotron ya hereda el bridge corregido. Qwen2.5 0.5B y SmolLM2 360M tienen los mismos hashes de catálogo en ambas apps. El bloque físico valida la integración de IsyMotron y sus diferencias de wrapper, sin partir de cero. [Detalle](../../audits/2026-10-21-manus/GUS_ISYCODE_REUSE.es.md).

## Global Constraints

- Cierre: **30 de octubre**, según el usuario; confirmar hora/zona. Entrega inicial objetivo: **28 de octubre**; 29 reservado a contingencias.
- Flujo principal: **PC + app móvil; web como panel de control**. Dispositivo físico: **iPhone 12**.
- La PC decide autoridad; GUS no recibe acceso a Link ni herramientas. Enviar una tarea requiere acción explícita de la persona.
- No iniciar remoto como respuesta automática a un fallo local. No copiar credenciales a logs, evidencia o repositorio.
- No inferir ejecución ni verificación a partir de `ALLOW`. Separar recibos de transporte, aprobación y ejecución.
- Mantener los pins del runtime y el catálogo; ningún modelo nuevo es requisito para cerrar los errores existentes.
- Desde el 27 de octubre: solo arreglos de fallos de entrega. Cada casilla requiere evidencia de aceptación antes de marcarse completa.

## Calendario

Las fechas son objetivos. Si un bloque se atrasa, se recortan extras; la demo y la entrega conservan su margen.

| Día | Fecha | Entregable del día | Criterio para cerrarlo |
|---|---|---|---|
| 1 | Mié 21 oct | Base de integración, protección del panel e instalación inicial en iPhone | Fuentes identificadas, estado privado protegido, app abre en el dispositivo; proveedor y cierre comprobados |
| 2 | Jue 22 oct | Panel conectado al contrato real | Sello inválido nunca verde; hosts, scopes, identidad y fechas correctos; datos viejos visibles |
| 3 | Vie 23 oct | GUS recuperable e integración offline validada | Salir durante carga funciona; error de chunk tiene recuperación; repetir en IsyMotron el funcionamiento offline de iSyCodeMovil |
| 4 | Sáb 24 oct | Tarea completa PC ↔ iPhone | Caso permitido, rechazado, cancelado y vencido; resultado y recibo corresponden a la misma tarea |
| 5 | Dom 25 oct | Modelo elegido y evidencia del iPhone 12 | Dos candidatos pequeños comparados; descarga/importación y recuperación probadas; decisión sobre NVIDIA nuevo cerrada |
| 6 | Lun 26 oct | Onboarding y uso sin ayuda del desarrollador | Un recorrido desde instalación limpia hasta recibo; errores accionables; sesión y segundo plano recuperables |
| 7 | Mar 27 oct | Candidato final reproducible | Checkout limpio, CI Python/web/móvil y builds; revisión exacta y guía de instalación verificadas |
| 8 | Mié 28 oct | Demo y entrega inicial | Video real, README, enlaces, artefactos y formulario preparados; entrega verificada por el dueño |
| 9 | Jue 29 oct | Contingencia | Corregir solo bloqueos de instalación, ejecución o entrega; comprobar acceso a los enlaces |

**30 de octubre:** comprobar el estado final del envío antes de la hora oficial; no reservar trabajo estructural para ese día.

## Qué cuenta como usable

- [ ] Instalar y abrir la build en el iPhone 12; registrar versión de iOS, firma y commit.
- [ ] Enlazar con una PC real usando el código; un código incorrecto falla sin degradar seguridad.
- [ ] Enviar una tarea explícita; ver estado; aprobar o rechazar; obtener el resultado correspondiente.
- [ ] Leer el mismo `task_id`/`receipt_id` y origen en las superficies donde se anuncie esa operación.
- [ ] Conversar localmente con un modelo pequeño en modo avión; cancelar y volver a intentarlo.
- [ ] Un fallo de red, permiso, modelo, sesión o sello se muestra como tal y tiene una salida.
- [ ] El panel web exige sesión, muestra datos reales y marca la antigüedad; no muestra payloads privados.
- [ ] Demostrar una acción dentro de scope y un rechazo fuera de scope con un host real.
- [ ] Repetir el flujo principal tres veces seguidas sin reiniciar manualmente servicios para rescatarlo.

## Mapa de trabajo

| Unidad | Archivos principales | Responsabilidad |
|---|---|---|
| Integración | Git, `docs/releases/`, `docs/mobile/ROADMAP.md` | Reunir trabajo revisado y registrar procedencia |
| Sesión web | `web/app/api/dashboard/route.ts`, nuevas rutas/módulo de sesión bajo `web/app/api/session/` y `web/lib/`, `web/app/page.tsx` | Autenticar visitante y expirar acceso; guardar el token backend solo en servidor |
| Proyección y UI | `web/lib/dashboard.js`, `web/lib/dashboard.test.mjs`, `web/app/page.tsx`, `console/server.py`, `core/isymotron/resources.py` | Adaptar el contrato real y representar evidencia sin ampliar autoridad |
| Carga GUS | `mobile/src/home.ts`, `mobile/src/main.ts`, nuevo E2E `mobile/e2e/gus-loading.e2e.mjs` | Navegación estable y recuperación de import |
| Tareas/permisos | `tools/link_task_runner.py`, `core/isymotron/link/server.py`, `core/isymotron/link/permissions.py`, sus tests | Ejecutar únicamente por el host y conservar coherencia de inbox/recibos |
| Modelos/iOS | `mobile/catalog/gus-models.json`, `mobile/ios/App/GusLocal/`, `mobile/tools/generate-gus-catalog.mjs` | Medir modelos existentes y empaquetar la selección verificada |
| Calidad/entrega | `.github/workflows/`, `web/package.json`, documentación y evidencia | Reproducibilidad, regresiones y demo |

Los módulos nuevos se mantienen pequeños y separados del render del panel. No se reorganiza el resto de la aplicación durante el cierre.

## Task 1: Base única, privacidad y riesgos físicos — día 1

**Files:** ramas `origin/master`, `origin/feature/isymotron-performance-1`, `claude/exciting-lamport-84gclk`; `web/app/api/dashboard/route.ts`; `web/lib/`; `web/app/api/session/`; `docs/releases/`.

**Interfaces:** consume el estado Python existente y el token backend solo en servidor. Produce una sesión web independiente, expirable, en cookie HttpOnly; `/api/dashboard` devuelve 401 sin sesión válida. Una proyección con campos permitidos evita enviar payloads/params privados. La integración registra el SHA base y las fuentes de cada grupo de commits.

- [ ] Crear una rama de integración aislada desde `origin/master`, prefijo `codex/`; preservar el checkout actual y la auditoría.
- [ ] Inventariar los commits móviles pendientes y los locales de runner/perfiles/TTL. Revisar cambios de autoridad y concurrencia antes de integrarlos; resolver conflictos conservando ambos flujos.
- [ ] Escribir una regresión con backend ficticio: sin sesión → 401; sesión vencida → 401; sesión válida → DTO permitido; canario privado ausente; token backend ausente en respuestas/cliente.
- [ ] Comprobar que falla antes del arreglo, implementar sesión propia con caducidad de una hora y logout; proteger cambios de sesión con validación de origen y comparación segura de credenciales. La credencial de acceso web es distinta de la del backend; la sesión usa cookies Secure cuando se sirve con HTTPS.
- [ ] Ejecutar las pruebas de sesión y `npm run build` de web; guardar evidencia HTTP sin secretos.
- [ ] Instalar una build conocida en el iPhone 12, probar arranque, anotar iOS y método de firma; cerrar pronto cualquier bloqueo de instalación.
- [ ] Probar una petición real al proveedor de la demo usando su configuración existente; confirmar requisitos oficiales del hackathon y registrar enlace, hora y zona de cierre. No cambiar ni crear llaves si no hace falta.
- [ ] Registrar commits y resultado de checks del bloque; preparar el cambio para revisión sin publicar automáticamente.

## Task 2: Datos y evidencia fieles — día 2

**Files:** `web/lib/dashboard.js`, `web/lib/dashboard.test.mjs`, `web/app/page.tsx`, `console/server.py`, `tests/test_console.py` y un E2E web con fixtures de contrato real.

**Interfaces:** consume `health.ok`, `awareness.snapshot`, `host.scopes`, `capability.summary`, `receipt.host`, `receipt.wall` en segundos, `seal_ok` y el tipo/origen de evidencia. Produce proyección por host con `observedAt`, `hostId`, `hostLabel`, estado de verificación y scopes lógicos. No adivina estados de hosts sin telemetría propia.

- [ ] Añadir fixtures generados por Python y regresiones para los hallazgos 2, 4, 5, 6 y 7; incluir dos hosts, sello falso, sello ausente, timestamp antiguo y campos opcionales ausentes.
- [ ] Verificar que las regresiones fallan y corregir el adaptador: usar `summary`, resolver `receipt.host`, convertir `wall`, conservar scopes lógicos y distinguir disponibilidad de energía/red.
- [ ] Corregir el flujo visual: `ALLOW` no completa por sí solo ejecución/verificación; distinguir verificado, inválido y desconocido. El backend publica esa distinción si el snapshot actual no alcanza.
- [ ] Añadir polling visible cada 5 segundos y caducidad visual a los 15; una petición activa, timeout y protección contra respuestas fuera de orden. Pausar en segundo plano y actualizar al volver.
- [ ] Verificar con reloj controlado que el fallo de red envejece el estado y nunca conserva «Ahora» indefinidamente; probar que reconectar recupera datos sin mezclar demo y real.
- [ ] Ejecutar unitarias web, prueba de contrato Python, E2E del panel y build. Guardar capturas del caso válido y del sello inválido.

## Task 3: Carga de GUS y validación de integración física — día 3

**Files:** `mobile/src/home.ts`, `mobile/src/main.ts`, `mobile/e2e/gus-loading.e2e.mjs`, scripts de `mobile/package.json` si se necesita incorporar el E2E.

**Interfaces:** conserva `AppDeps.gus` y el controlador existente. Una carga pendiente pertenece a la navegación que la inició; abandonar la pantalla invalida su efecto visual. Un import fallido presenta reintento o recarga explícitos, sin perder la identidad Link.

- [ ] Convertir los reproductores de los hallazgos 8 y 9 en regresiones E2E: chunk retenido + volver a Inicio, y chunk abortado + recuperación de red.
- [ ] Comprobar sus fallos y añadir invalidación de navegación, restablecimiento de carga rechazada y recuperación explícita cuando el navegador cachee el fallo de import.
- [ ] Probar doble toque del launcher, salir/entrar varias veces y dejar que llegue una descarga antigua; comprobar ausencia de suscripciones duplicadas.
- [ ] Ejecutar `npm test`, `npm run build`, `npm run e2e` y `npm run e2e:gus`, más el E2E nuevo.
- [ ] En iPhone: descargar/verificar SmolLM2 360M o Qwen 0.5B; cargar con contexto 512 y salida 64; activar modo avión y generar una respuesta real. Registrar si pasa o el fallo concreto.
- [ ] Priorizar el Qwen 0.5B ya probado por el usuario en iSyCodeMovil y repetir en IsyMotron; identificar la variante de Smol. Registrar ambas builds sin confundir el antecedente físico con la validación del wrapper Capacitor.

## Task 4: Tarea de extremo a extremo — día 4

**Files:** `tools/link_task_runner.py`, `core/isymotron/link/server.py`, `core/isymotron/link/permissions.py`, `tests/test_link_task_runner.py`, `tests/test_link_task_runner_permissions.py`, `mobile/e2e/pairing.e2e.mjs`, `mobile/src/home.ts`, `console/server.py`.

**Interfaces:** `task_id` identifica un envío; la PC conserva la decisión y publica el estado; `receipt_id` identifica evidencia real. El servidor y runner deben compartir un mecanismo de actualización consistente, no competir mediante lecturas/escrituras completas del inbox. Las proyecciones de recibos distinguen transporte, aprobación y ejecución.

- [ ] Añadir regresiones de tarea permitida, rechazada, cancelada y vencida; caída del runner durante una tarea; solicitud de permiso sin respuesta; dos envíos simultáneos y un reintento del cliente.
- [ ] Verificar que ninguna carrera pierde mensajes ni duplica ejecución. Si un reinicio deja un resultado ambiguo, mostrar estado no confirmado y pedir revisión; no ejecutar de nuevo automáticamente.
- [ ] Integrar el runner y los perfiles revisados con arranque/parada documentados, manteniendo la política por defecto y el enforcer.
- [ ] Verificar evidencia del runner antes de mostrarla en el panel; comprobar la correlación con `task_id`. Si requiere adaptador, hacerlo de solo lectura con proyección lógica, sin confiar en JSON de chat ni etiquetas de texto.
- [ ] Probar el flujo con iPhone 12 y PC real en la misma red: lectura dentro de una carpeta de demo; petición fuera de scope; aprobación y rechazo. No usar documentos privados como fixtures.
- [ ] Repetir tres veces y guardar evidencia con SHA de la build, IDs y resultados; los mocks no cierran esta casilla física.

## Task 5: Modelo pequeño elegido — día 5

**Files:** catálogo existente, `mobile/ios/App/GusLocal/`, guía GUS y nuevo registro físico bajo `evidence/IPHONE12_GUS_V1/`.

**Interfaces:** mantiene el catálogo fijado por revisión, tamaño y SHA-256. Produce un informe físico de SmolLM2 360M y Qwen2.5 0.5B con decisión de cuál se recomienda en este dispositivo.

- [ ] Probar los dos modelos existentes con 10 prompts fijos de orientación en español; medir arranque/carga, primera respuesta o primer token si el runtime lo expone, tiempo total, cancelación y estabilidad. Separar medición de salida real de una estimación.
- [ ] Reutilizar el caso «Don Zelaya» del smoke test de iSyCodeMovil como regresión de repetición. Comprobar que sigue usando el sampling corregido; evaluar exactitud por separado. Comparar también la carga repetida de IsyMotron frente al contexto persistente de iSyCodeMovil y adaptar sus utilidades de memoria/diagnóstico si la medición lo justifica.
- [ ] Probar contexto 512 y 1,024; ampliar hasta 2,048 solo si es estable. Probar 10 minutos de uso y registrar cierres, avisos térmicos y memoria solo cuando pueda medirse.
- [ ] Verificar modo avión, descarga interrumpida, espacio insuficiente, GGUF corrupto, exportar/importar y reiniciar la app; no eliminar el modelo anterior antes de validar el reemplazo.
- [ ] En el iPhone, verificar también remoto explícito con el proveedor permitido: petición real, error visible de credencial/red, ausencia de fallback y regreso manual a local. Las pruebas con mocks no sustituyen este recorrido; las capturas nunca incluyen la llave.
- [ ] Cerrar el experimento NVIDIA: confirmar identificador y tarea del modelo propuesto. El Embed 1B encontrado no se añade al chat. Otro generativo solo entra si formato, runtime, procedencia, licencia y rendimiento físico pasan sin una migración importante.
- [ ] Elegir el modelo por los resultados, publicar sus limitaciones reales y guardar evidencia. Si ninguno cumple el objetivo del spec, priorizar arreglar la inferencia local; no simularla ni anunciar remoto como offline.

## Task 6: Uso cotidiano y onboarding — día 6

**Files:** `mobile/src/home.ts`, `mobile/src/styles.css`, `web/app/page.tsx`, `web/app/globals.css`, guías CLI/móvil/web.

**Interfaces:** conserva el flujo de autoridad; cada estado de error ofrece una acción disponible y clara: reintentar, volver, comprobar la PC o recargar. El monitor identifica el origen y antigüedad de los datos.

- [ ] Recorrer instalación → configurar PC → enlazar → verificar conexión → ejecutar/rechazar → leer recibo siguiendo solo la guía.
- [ ] Probar bloqueo/desbloqueo del iPhone, segundo plano, pérdida de Wi-Fi y expiración de sesión; conservar identidad y representar correctamente solicitudes pendientes.
- [ ] Corregir Escape, foco y cierre del drawer web; usar imagen estática con movimiento reducido. Etiquetar el acceso como ayuda/estado mientras el chat web esté fuera de alcance.
- [ ] Evitar botones sin efecto, estados de éxito ficticios y mensajes «conectado» basados únicamente en un emparejamiento guardado.
- [ ] Registrar duración y pasos manuales del onboarding; corregir los bloqueos encontrados sin abrir un rediseño general.

## Task 7: Candidato final reproducible — día 7

**Files:** `.github/workflows/ci.yml`, `.github/workflows/mobile.yml`, nueva `.github/workflows/web.yml`, `web/package.json`, documentación de release y manifiesto de evidencia.

**Interfaces:** el mismo SHA pasa Python, web y móvil y produce los artefactos usados en la demo. El job web corre instalación limpia, pruebas de sesión/contrato, build y E2E relevante.

- [ ] Incorporar las regresiones a CI y ejecutar desde un checkout limpio; no reutilizar `node_modules` de otro snapshot para el candidato final.
- [ ] Correr Python, web y móvil, comprobación de catálogo/runtime y E2E; construir los paquetes existentes y comprobar empaquetado del framework iOS.
- [ ] Instalar la build candidata exacta en el iPhone y repetir el flujo principal. Registrar cualquier diferencia respecto al artefacto firmado/instalado.
- [ ] Preparar assets, hashes, notas de versión y pasos de recuperación; revisar que no contengan secretos ni datos personales.
- [ ] Congelar funcionalidades. Una casilla con prueba omitida no se transforma en demostrada por tener CI verde.

## Task 8: Demo y entrega — días 8 y 9

**Files:** README y materiales del hackathon, guía corta, enlaces a artefactos y evidencia de la revisión candidata.

**Interfaces:** la presentación describe las funciones realmente probadas; el dueño realiza o autoriza el envío final conforme a las reglas oficiales.

- [ ] Grabar una demo real: GUS local sin red; recuperar Wi-Fi; enlazar; enviar tarea; aprobación y ejecución; solicitud fuera de scope rechazada; revisar recibo y panel.
- [ ] Mostrar el papel de Nemotron/proveedor que exijan las reglas con evidencia real. No confundir el pequeño modelo local elegido con un modelo NVIDIA distinto.
- [ ] Usar la duración y campos exigidos por el hackathon, confirmados el día 1. Preparar resumen, instrucciones, limitaciones y enlaces accesibles.
- [ ] El 28: completar la entrega inicial y comprobar el estado del envío junto con el dueño. No marcarla enviada por haber preparado los archivos.
- [ ] El 29: corregir solo bloqueos, verificar enlaces desde una sesión limpia y guardar una copia de la entrega final.

## Review Focus

Estos cinco escenarios tienen pruebas asignadas arriba y se vuelven a comprobar sobre la revisión final:

1. Sesión ausente/vencida con backend accesible: nunca devolver estado privado — Task 1.
2. Sello falso o campo ausente y dos hosts: nunca pintar evidencia verde ni atribuirla al primer host — Task 2.
3. Respuesta de red fuera de orden o segundo plano: nunca rejuvenecer datos antiguos — Task 2.
4. Navegar mientras carga o fallar un import: recuperación sin salto forzado de pantalla — Task 3.
5. Runner y Link escribiendo a la vez, reintento o reinicio: no perder tareas ni repetir ejecuciones — Task 4.

## Cobertura de la auditoría

| Hallazgo | Trabajo que lo cierra |
|---|---|
| 1 · Proxy sin sesión | Task 1 |
| 2 · Falso sello | Task 2 |
| 3 · Ramas incompletas | Task 1 y candidato final Task 7 |
| 4 · Cero hosts activos | Task 2 |
| 5 · Tiempos/frescura falsos | Task 2 |
| 6 · Host incorrecto en recibo | Task 2 |
| 7 · Descripciones/scopes ausentes | Task 2 |
| 8 · Navegación de GUS | Task 3 |
| 9 · Import fallido bloqueado | Task 3 |

## Comandos de verificación

Desde la raíz del checkout de integración, para el bloque Python:

```bash
python -m pytest -q -rs
```

Desde `web/`, para el panel (ampliar el script de test para incluir sesión y contrato cuando se creen):

```bash
npm ci
npm test
npm run build
```

Desde `mobile/`, para app y runtime:

```bash
npm ci
node tools/sync-gus-runtime.mjs --verify
node tools/generate-gus-catalog.mjs --check
npm test
npm run build
npm run e2e
npm run e2e:gus
```

Incorporar además los nuevos E2E de carga GUS y panel a los scripts y a CI. Cada comando debe terminar con exit 0 y sin fallos. Comparar las omisiones de Python con el sistema probado; no exigir un conteo fijo si se añaden regresiones. El modo E2E modifica `dist/`: reconstruir producción antes de empaquetar y verificar de nuevo que no incluya mocks. La aceptación física se registra por separado y nunca se sustituye por estos comandos.

## Recortes si hay atraso

Se eliminan primero: nuevo modelo experimental, animaciones adicionales y extras visuales. Se mantiene el modelo pequeño que ya funcione. El chat web completo, nuevos sistemas de búsqueda y nuevas plataformas físicas no entran a esta entrega.

Si la firma del iPhone falla, se atiende el día 1. Si local no funciona, no se anuncia offline hasta resolverlo. Si la integración introduce regresiones de autoridad, se conserva una revisión conocida para comparar y se corrigen antes de publicar; no se desactiva la política para que la demo pase.

## Estado inicial

**Hecho:** auditoría, reproducción de nueve hallazgos y este roadmap con el alcance elegido. **Pendiente:** implementar, integrar y validar cada bloque. Las casillas reflejan trabajo restante y no se completan por haberlo planificado.
