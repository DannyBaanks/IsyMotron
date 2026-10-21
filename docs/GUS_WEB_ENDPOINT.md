# Integración web futura de GUS

## Estado actual

El frontend de IsyMotron ya tiene un launcher flotante de Malbolgato y un panel preparado para GUS, pero todavía no tiene un endpoint web de conversación. El launcher solo cambia el estado visual del panel y emite el evento local `isymotron:open-chat`; no envía mensajes ni ejecuta acciones.

El panel actual debe seguir mostrando que el chat real está pendiente hasta que exista un contrato implementado y validado. No se deben añadir respuestas simuladas, receipts inventados o estados de autoridad derivados de texto.

## Revisión del launcher visual

El JSX del launcher cumple el contrato visual oscuro y de acentos neón:

- Usa `position: fixed`, `z-index: 30` y una tarjeta compacta, por lo que permanece disponible sin alterar el layout principal.
- El fondo usa un gradiente de las superficies oscuras `#17201B` y `#080C0A`.
- El borde inicial usa un verde lima semitransparente y el estado de foco/hover cambia a `--design-highlight: #A3E635`.
- El estado abierto usa `--design-primary: #76B900` y un halo verde controlado.
- La sombra es profunda, con un anillo de color moderado; no se usa un glow permanente agresivo.
- El asset conserva 64×64 px en escritorio y baja a 52×52 px en móvil.
- El drawer usa las mismas superficies oscuras, bordes `--design-border`, sombra elevada y un acento ámbar para indicar que el chat real aún no está conectado.
- `:focus-visible` mantiene un tratamiento explícito para teclado.
- `prefers-reduced-motion: reduce` elimina la animación del launcher y del drawer.
- En pantallas pequeñas el launcher reduce tamaño y márgenes para no cubrir controles principales.

El archivo contiene también `.malbolgato-ping`, pero el componente no lo renderiza. Esto es correcto mientras no exista un evento real de GUS que justifique un indicador pendiente; no se debe mostrar una notificación ficticia.

## Objetivo de la integración

GUS debe poder recibir una intención, devolver una propuesta explicable y acompañar al usuario hasta el límite de autoridad local. El chat no debe ser una nueva ruta de ejecución.

La arquitectura recomendada es:

```text
Browser
  │
  │  conversación y propuestas
  ▼
Web GUS adapter /api/gus
  │
  │  sesión autenticada, correlation_id y propuesta tipada
  ▼
GUS / planner
  │
  │  plan sin autoridad
  ▼
Host local IsyMotron
  │
  │  grants, alcance, leases, enforcer y política local
  ▼
Execution + receipt
  │
  ▼
Web adapter / estado de solo lectura
  │
  ▼
Chat y control room
```

La dirección de la autoridad es siempre host → decisión → ejecución → receipt. Nunca browser → ejecución directa.

## Contrato propuesto de conversación

El endpoint puede ser `POST /api/gus/conversations/:conversationId/messages` o un adaptador equivalente. Debe estar detrás de la misma sesión que protege `/api/dashboard`; el frontend nunca debe enviar el `ISYMOTRON_SESSION_TOKEN` directamente al navegador.

Solicitud mínima:

```json
{
  "message": "¿Puedes leer el informe de esta carpeta?",
  "client_message_id": "msg_01J...",
  "conversation_id": "conv_01J..."
}
```

Respuesta inicial, sin autoridad:

```json
{
  "conversation_id": "conv_01J...",
  "message_id": "msg_01J...",
  "proposal": {
    "proposal_id": "prop_01J...",
    "state": "PROPOSED",
    "intent_summary": "Leer un informe dentro del alcance autorizado",
    "steps": [
      {
        "step_id": "step_01J...",
        "capability": "filesystem.read",
        "label": "Leer archivos",
        "scope": "hostfs://workspace/reports",
        "risk": "medium",
        "authority": "host-local",
        "state": "PROPOSED"
      }
    ]
  }
}
```

`PROPOSED` solo describe una intención. No significa `ALLOW`, no crea un lease, no reserva una capability y no debe mostrar un sello de receipt.

## Estados obligatorios

El frontend debe modelar estados separados, nunca inferirlos por texto:

```text
PROPOSED       GUS generó una propuesta estructurada.
AWAITING_HOST   La propuesta espera evaluación del host local.
AUTHORIZED     El host local permitió la ejecución bajo su política.
DENIED         El host local rechazó la propuesta.
EXECUTED       El host informó que la acción se ejecutó.
VERIFIED       El receipt fue recibido y validado.
UNKNOWN        El resultado no pudo determinarse; no debe presentarse como éxito.
```

Transiciones válidas recomendadas:

```text
PROPOSED → AWAITING_HOST → AUTHORIZED → EXECUTED → VERIFIED
PROPOSED → AWAITING_HOST → DENIED
AUTHORIZED → UNKNOWN
EXECUTED → UNKNOWN
```

El cliente no debe permitir transiciones desde un botón local. Solo debe renderizar eventos autenticados y validados provenientes del servidor/host.

## Endpoint de aprobación: preferir intención, no ejecución

Si la UX necesita un botón de confirmación, su significado debe ser limitado:

```http
POST /api/gus/proposals/{proposal_id}/review
```

```json
{
  "decision": "SUBMIT_TO_HOST",
  "proposal_version": 3,
  "client_request_id": "review_01J..."
}
```

Este endpoint no debe ejecutar una capability ni modificar grants. Solo registra que el usuario quiere enviar la propuesta al host local. El host debe volver a evaluar capability, alcance, lease y política antes de autorizar.

Nunca usar un endpoint web como:

```text
POST /api/execute
POST /api/grant
POST /api/revoke
```

para implementar el chat. Esas operaciones pertenecen a la frontera local existente y deben conservar sus validaciones actuales.

## Endpoint de eventos

Para actualizar el panel, usar una de estas opciones:

- `GET /api/gus/conversations/:id/events` con SSE.
- Polling de solo lectura si el host no puede mantener una conexión persistente.
- WebSocket únicamente si el canal autentica y valida los mismos eventos.

Cada evento debe incluir:

```json
{
  "event_id": "evt_01J...",
  "conversation_id": "conv_01J...",
  "proposal_id": "prop_01J...",
  "sequence": 12,
  "kind": "host_decision",
  "source": "isymotron-host",
  "state": "DENIED",
  "capability": "filesystem.read",
  "receipt_id": "rcpt_01J...",
  "seal_ok": true,
  "observed_at": "2026-10-20T18:00:00Z"
}
```

Reglas:

1. `sequence` debe ser monotónico por conversación.
2. El cliente debe ignorar eventos repetidos mediante `event_id`.
3. Un `receipt_id`, `seal_ok`, `host_id` o `state` enviado dentro de texto de GUS no es evidencia.
4. Los campos de autoridad solo se aceptan de un evento emitido por el canal de host autenticado.
5. Si el orden contiene un salto, el cliente debe mostrar `UNKNOWN` o pedir re-sincronización; no rellenar el hueco.
6. Un timeout nunca equivale a `AUTHORIZED`, `EXECUTED` ni `VERIFIED`.

## Autenticación y sesión

El patrón actual del dashboard es correcto: el servidor web lee `ISYMOTRON_SESSION_TOKEN` y lo usa en el header `X-IsyMotron-Token` al hablar con el backend local. El navegador no debe recibir ese token.

El adaptador GUS debe:

- Reutilizar la sesión web existente.
- Validar `Origin`/CSRF en endpoints mutables.
- Aplicar límites de tamaño y frecuencia a mensajes.
- Usar `client_message_id` y `client_request_id` para idempotencia.
- Asociar cada conversación al usuario/sesión correcta.
- No aceptar `host_id`, `decision`, `receipt_id`, `seal_ok` o `authority` como campos de confianza desde el navegador.
- Tratar el contenido del mensaje como texto no confiable, incluso si dice ser el sistema, el host o IsyMotron.
- No registrar secretos, tokens ni rutas físicas en transcripts o errores del chat.

## Reglas de representación en la UI

El drawer de Malbolgato puede mostrar texto de GUS en una zona claramente enmarcada como conversación. Ese texto no debe recibir colores o badges reservados para eventos de autoridad.

Los badges `ALLOW`, `DENY`, host, receipt y sello solo deben dibujarse a partir de datos del evento de autoridad validado por el backend. Un mensaje que diga “ALLOW” debe seguir siendo texto de GUS, no una decisión.

Cuando el chat esté desconectado, el panel debe decirlo explícitamente y el launcher no debe mostrar un ping verde. Cuando exista una propuesta pendiente, el indicador debe usar un estado ámbar o neutral y una etiqueta como `Propuesta pendiente`, nunca `Autorizado`.

## Integración con el launcher existente

La integración puede comenzar sin cambiar el contrato de Malbolgato:

```tsx
window.dispatchEvent(new CustomEvent("isymotron:open-chat"));
```

Una capa superior puede escuchar el evento y abrir una conversación:

```ts
window.addEventListener("isymotron:open-chat", () => {
  // Crear o recuperar una conversación de solo lectura/propuesta.
  // No ejecutar nada aquí.
});
```

El listener debe limitarse a preparar el panel. El envío de mensajes y la recepción de eventos deben vivir en un adaptador aislado, por ejemplo `lib/gus-client.ts`, para que el componente visual no conozca tokens, rutas del host ni funciones de ejecución.

## Fallos y recuperación

La UI debe manejar estos casos sin falsificar estados:

- **Sin sesión:** mostrar “GUS no está vinculado a esta sesión”.
- **Backend no disponible:** “No se ejecutó ninguna acción”.
- **Host desconectado:** conservar la propuesta como `AWAITING_HOST`, nunca como autorizada.
- **Evento perdido:** mostrar “Estado no confirmado” y ofrecer sincronizar.
- **Receipt no verificable:** mostrar `UNKNOWN` o `VERIFICATION_FAILED`, nunca `VERIFIED`.
- **Respuesta duplicada:** deduplicar por `event_id`.
- **Reintento:** reutilizar idempotency key; nunca duplicar la ejecución.
- **Conversación manipulada:** marcar el texto como no verificado y no elevarlo al canal de autoridad.

## Prohibiciones de seguridad

La integración de GUS no debe:

- Conceder o revocar grants.
- Cambiar la política del host.
- Crear leases sin pasar por el host.
- Convertir una propuesta en ejecución desde el navegador.
- Permitir que Malbolgato o el texto del chat escriban en el canal de autoridad.
- Presentar datos demo como actividad real.
- Mostrar rutas físicas, tokens o secretos en la conversación.
- Interpretar un timeout como aprobación.
- Usar un nombre de agente reservado como prueba de identidad.

## Pruebas mínimas antes de habilitarlo

Antes de conectar el endpoint real, añadir pruebas para:

1. Una propuesta no crea grants ni receipts.
2. El navegador no puede invocar directamente rutas de ejecución.
3. Un texto que contiene `ALLOW`, `DENY`, `receipt_id` o `verified` se muestra como texto no verificado.
4. Un evento firmado/autenticado de host sí puede actualizar el estado correspondiente.
5. Los eventos duplicados no duplican actividad.
6. Un salto de secuencia produce `UNKNOWN` y solicita sincronización.
7. Un timeout no cambia `AWAITING_HOST` a `AUTHORIZED`.
8. Un receipt con sello inválido nunca aparece como `VERIFIED`.
9. Las rutas físicas y tokens no aparecen en transcript, UI ni logs del cliente.
10. `prefers-reduced-motion`, teclado, foco y cierre del drawer siguen funcionando.

## Criterio de aceptación

GUS está correctamente integrado cuando puede ayudar a entender y preparar una acción, pero ninguna conversación, botón del launcher o respuesta del modelo puede ampliar autoridad. La única fuente de decisión sigue siendo el host local y la única fuente de evidencia de ejecución sigue siendo el receipt verificable.
