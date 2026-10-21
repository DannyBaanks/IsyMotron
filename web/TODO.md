# Entregables — ISYMOTRON_DESIGN_V1

## Experiencia principal para usuarios no técnicos
- [x] La pantalla principal explica con jerarquía visual clara que la IA propone, el host local decide y cada acción genera un recibo verificable.
- [x] La navegación usa etiquetas comprensibles y permite saltar a Resumen, Flujo, Actividad, Recibos y Hosts.
- [x] Los indicadores de conexión, disponibilidad del backend, estado de hosts y condición de seguridad son fáciles de interpretar.
- [x] La sidebar conserva la navegación actual, con estado activo, contraste mejorado y responsive compacto en pantallas pequeñas.
- [x] El Home prioriza autoridad, equipos, capacidades, receipts y actividad sin añadir tarjetas decorativas innecesarias.

## Design system compartido
- [x] La UI declara los tokens canónicos compartidos `ISYMOTRON_DESIGN_V1`: `#080C0A`, `#111815`, `#17201B`, `#29372F`, `#76B900`, `#A3E635`, `#F3F7F4`, `#A6B2AA`, `#738179`, `#7296FF`, `#EFB84B` y `#FF6767`.
- [x] El tratamiento visual usa negro profundo, superficies elevadas, bordes discretos, verde de acción, jerarquía legible, sombras moderadas y movimiento mínimo, sin usar marcas ni logos propietarios de NVIDIA.
- [x] La UI sigue siendo técnica y premium sin convertirse en terminal ni depender únicamente del color para comunicar estados.
- [x] La barra de confianza separa conexión, autoridad, frescura de datos y evidencia para no confundir “conectado” con “autorizado”.
- [x] La vista simple oculta complejidad y el control opcional “Detalles técnicos” revela host_id, power_epoch y network solo cuando el usuario lo solicita.

## Flujo, actividad, capabilities y receipts
- [x] La visualización conserva el flujo conceptual IA propone → equipo decide → ejecución → receipt, diferenciándolo de la evidencia de una operación real.
- [x] La actividad reciente muestra estados, tiempos y resultados de forma escaneable y sin apariencia de consola técnica.
- [x] Los receipts muestran listado, filtro, detalle expandible, capability, equipo, resultado, sello e identificador sin inventar hashes ni autoridad.
- [x] La sección de hosts muestra identidad, conexión, permisos y disponibilidad sin modificar los contratos existentes.
- [x] El catálogo de capabilities muestra nombre legible, identificador técnico, estado y los campos de descripción, alcance y riesgo cuando existen; los campos ausentes se expresan como “No especificado” y nunca se inventan.
- [ ] El backend debe exponer de forma completa autoridad requerida y estados adicionales PENDING/DENIED/UNKNOWN para que el catálogo pueda mostrar más contexto real.
- [x] La actividad y receipts renderizan fecha, acción, owner, origen y frescura cuando esos campos opcionales llegan del backend, y mantienen un fallback honesto cuando no están disponibles.
- [ ] El backend debe exponer de forma consistente fecha, acción y owner reales en todos los receipts para eliminar el fallback del snapshot reducido actual.

## Malbolgato y GUS
- [x] El GIF original de Malbolgato fue copiado desde `avatar/packs/malbolge-cat/idle.gif` a `public/malbolgato/idle.gif`, con procedencia documentada.
- [x] Existe un launcher flotante accesible, responsive y compatible con teclado, con etiqueta “Abrir chat de ISyMotron”, respetando `prefers-reduced-motion`.
- [x] Malbolgato se presenta como companion que representa y no autoriza; no concede permisos, modifica políticas ni ejecuta acciones.
- [ ] El launcher debe abrir el chat real de GUS y conservar conversación/estado cuando exista un endpoint o integración web real. La superficie actual no expone ese endpoint, por lo que esta condición queda NOT VERIFIED y no se simulan mensajes.
- [x] El panel actual distingue PROPOSED, AUTHORIZED, EXECUTED, VERIFIED y DENIED como conceptos separados, sin presentarlos como equivalentes.

## Estados, responsive, seguridad y arquitectura
- [x] El modo demo permanece identificado como demostración y no se mezcla con backend en vivo; los datos demo siguen claramente marcados.
- [x] El onboarding explica en tres pasos cómo iniciar el host local, confirmar la sesión y revisar capabilities, sin mostrar secretos ni prometer una conexión inexistente.
- [x] La interfaz contempla checking, datos vacíos, desconexión, error, reintento y recuperación sin falsificar autoridad.
- [x] La experiencia conserva claridad en escritorio, tablet y móvil; el launcher evita tapar controles principales.
- [x] La interfaz incluye foco visible, semántica, contraste y comunicación de estados no dependiente solo del color.
- [x] Se preservan Authority, GUS, Link, execution owners, receipts, permisos, sesiones, autenticación y contratos API existentes; este cambio solo añade UI, asset y estilos.
- [x] No se ampliaron permisos, no se eliminaron validaciones, no se expusieron credenciales y no se modificó la arquitectura de ejecución/autorización.

## Verificación y entrega
- [x] `npm test` pasa las pruebas existentes.
- [x] `npm run build` compila en producción.
- [x] `GET /manus-routes.json` responde HTTP 200 con la ruta pública `/`.
- [x] Preview fue revisado visualmente en escritorio y móvil después del cambio visual.
- [x] El asset de Malbolgato existe y se sirve desde la aplicación.
- [ ] La integración de chat real y sus flujos E2E quedan pendientes hasta disponer del endpoint web correspondiente.
