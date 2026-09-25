# IsyMotron Link — guía

Enlaza dos oficinas IsyMotron en la misma red (misma máquina dos veces en el demo) para delegar trabajo de unos a otros sin instalar nada extra ni compilar un ejecutable. Todo es stdlib Python; sin React, sin npm, sin binarios.

## El comando

En **las dos máquinas** (o dos `XDG_STATE_HOME` distintos, como en el demo):

```bash
isymotron link servir    # en la que va a recibir trabajo (la otra no hace falta)
isymotron link emparejar 127.0.0.1:47931
# te da un código de 6 dígitos; en la otra:
isymotron link aceptar <codigo>
```

Después:

```bash
isymotron link enviar <oficina> "tu tarea" --titulo "corto"
isymotron link tarea <oficina> <task_id>
isymotron link mensaje <oficina> <task_id> "contexto"
isymotron link cancelar <oficina> <task_id> ["motivo"]
isymotron link estado          # esta oficina + enlazadas + inbox
isymotron link buscar          # discovery por broadcast (lista, no confía)
isymotron link olvidar <oficina>  # unilateral: ella te recuerda hasta olvidarte
```

La consola web tiene panel en `/link` (mismo token de sesión que el resto de la consola; el avatar de solo-lectura no puede delegar).

## La regla de oro

**Solo acepta un código que estés viendo en la otra pantalla.** Emparejar da permiso a esa máquina de dejarte tareas en tu inbox. Si el código no coincide, no aceptes.

## Cómo funciona (en corto)

```text
Oficina A                                        Oficina B
isymotron link enviar ──sobre sellado──▶ POST /link/v1/call ──▶ inbox de B
      ▲                                         ▲
      └─────────link tarea (estado)─────────────┘
```

- Identidad = par Ed25519 (firma) + X25519 (cifrado); el `office_id` es la huella SHA-256 de la llave pública de firma. Una oficina no puede mentir quién es.
- Cada llamada va **firmada** (Ed25519) y **cifrada** (X25519 DH → HKDF-SHA256 → AES-128-GCM). Sobre repetido, alterado, viejo o no dirigido a ti: rechazado.
- El código de 6 dígitos se deriva de **las dos llaves y los dos nonces** (ordenado): un MITM no puede hacer que ambas pantallas muestren lo mismo.
- Delegar solo deja la tarea en el inbox de la otra oficina (`queued`). Nunca toca tu sesión ni tus terminales.
- Recibo en ambos lados de cada delegación: `link_delegated` en quien envía, `link_received` en quien recibe (`~/.local/state/isymotron/link/receipts.jsonl`).

## Los comandos, uno por uno

Todo lo de abajo se ejecutó el 2026-09-25 con dos oficinas en la misma máquina (estados aislados con `XDG_STATE_HOME`, servidor en `127.0.0.1:47931`).

### Emparejar (en la que pide)

```console
$ isymotron link servir &
$ XDG_STATE_HOME=/tmp/lB isymotron link servir --port 47931 --udp-port 47932 &
# (en la otra:)
$ XDG_STATE_HOME=/tmp/lA isymotron link emparejar 127.0.0.1:47931 --si
Emparejando isytron-dannyisyco -> isytron-dannyisyco (127.0.0.1:47931)
Huella: 9fab 99d9 e557 1b1a

Código:  652 339

En la otra máquina corre:  isymotron link aceptar  y revisa que muestre este mismo código.
listo de este lado. Prueba: isymotron link enviar isytron-dannyisyco "hola"
```

`--si` salta la confirmación humana para pruebas automatizadas. Sin él, el CLI pregunta `[s/N]`.

### Aceptar (en la otra)

```console
$ XDG_STATE_HOME=/tmp/lB isymotron link aceptar 652339
enlazada con isytron-dannyisyco. Ya puede delegarte trabajo.
```

Las solicitudes duran 10 minutos. Código malo: `código no coincide con ninguna solicitud pendiente.` (exit 1), sin confiar en nadie.

### Delegar y seguir

```console
$ XDG_STATE_HOME=/tmp/lA isymotron link enviar isytron-dannyisyco "Audita el port y dame resumen" --titulo "M5 demo: delegacion link"
delegada a isytron-dannyisyco → task-1790333128891-cae4
sigue: isymotron link tarea isytron-dannyisyco task-1790333128891-cae4

$ XDG_STATE_HOME=/tmp/lA isymotron link tarea isytron-dannyisyco task-1790333128891-cae4
  M5 demo: delegacion link  queued
```

### Estado

```console
$ XDG_STATE_HOME=/tmp/lB isymotron link estado
ESTA OFICINA
  isytron-dannyisyco  4454 1296 9f4d 5c99

ENLAZADAS
  - isytron-dannyisyco  9fab99d9e5571b1a
inbox: 1 en cola
```

## Cómo leer lo que ves

| Ves | Significa | Qué hacer |
|---|---|---|
| `enlazada con X` | La otra aceptó tu código y te pinó | Nada |
| `código no coincide` | Escribiste mal el código o no hay solicitud viva | Repite `emparejar` |
| `oficina no emparejada` | No la conoces: olvidó o reinstaló | `emparejar` de nuevo |
| `sin respuesta de X` | No llega: enlace apagado, otra red o firewall | En la otra: `link servir` |
| `sobre fuera de tiempo` | Los relojes difieren más de 2 minutos | Ajusta hora en ambas |
| `unknown office (not paired)` | El remoto no te tiene pinado | `aceptar` en el remoto |
| `no pude abrir :47931` | Ya hay un `link servir` corriendo ahí | Mátalo: `kill <pid>` (ver trampa 1) |

## Trampas

1. **Servidor fantasma en el mismo puerto.** Si el puerto ya estaba tomado, `servir` antes M5 fallaba con traceback crudo y tú pensabas que era el nuevo. Ahora dice: `no pude abrir :47931 — ¿ya hay un 'link servir' corriendo?`. Encuentra al zombi: `ss -tlnp | grep 47931` y mátalo por PID. Me lo caché a mí mismo corriendo el demo M5.
2. **`nonces` anti-replay viven en memoria del servidor.** Si el servidor reinicia, olvida los nonces viejos y podría aceptar uno repetido dentro de su ventana de 2 minutos. Para el demo no pasa; para producción hay que persistirlos (post-M5).
3. **Discovery por broadcast solo lista, no confía.** `buscar` muestra oficinas en la red, pero `enviar` a una no emparejada falla en el servidor. Confía solo con el código.
4. **Olvidar es de un solo lado.** Si tú olvidas a X, X te sigue conociendo hasta que ella también te olvide (y viceversa). No es un bug: el patín es no asumir que cortar por tu lado corta por ambos.
5. **El token de sesión de la consola abre `/link`, no el avatar de solo-lectura** (R5: el avatar nunca escribe).
6. **Puertos por defecto** son 47931/tcp + 47932/udp (fijos en M0 para no colisionar con el pet 8760 ni con Munder 47831/47832 si coexisten).

## NO PROBADO

- Entre dos máquinas físicas distintas: todo lo de arriba se probó con dos oficinas en la misma computadora (dos `XDG_STATE_HOME` distintos). El protocolo es el mismo, pero ni firewall real ni relojes distintos ni MTU reales se ejercitaron.
- En Windows, Docker, Tailscale: no corrí. La librería es stdlib y debería funcionar, pero no se ha probado.
- Persistencia de nonces entre reinicios del servidor (ver trampa 2).
- Delegar automáticamente según RAM/CPU/capacidad (Munder documenta la misma no-demostración; el estado ya lo trae, la política no).
