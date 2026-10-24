# NVIDIA NIM desde iPhone físico — 2026-10-06

Status: `NOT_DEMONSTRATED` (prueba física pendiente de ejecución por el owner).

## Objetivo

Demostrar un round trip real: app IsyMotron Móvil en iPhone físico → modo remoto GUS →
NVIDIA NIM (`https://integrate.api.nvidia.com/v1`) → respuesta de Nemotron → sin
exponer API key → errores NIM visibles → sin fallback silencioso → regreso a local
solo por acción explícita.

## Environment

| Fact | Value |
|---|---|
| Date (UTC) | PENDIENTE |
| Device | iPhone del owner |
| App version | `1.2.0-rc.2` (`IsyMotron-ios-unsigned.ipa`) |
| App commit en la build | `fbada5d..70bf0f5` (tag `v1.2.0-rc.2`) |
| PC host | Linux, misma Wi-Fi (solo para Link; este test es phone→NIM) |
| Provider | NVIDIA NIM |
| Base URL | `https://integrate.api.nvidia.com/v1` |
| Model | `nvidia/nemotron-3-nano-30b-a3b` (del preset de la app) |
| Key | NVIDIA NIM key; NUNCA escrita en esta carpeta, logs ni capturas |

## Prueba 1 — round trip real (DEMOSTRADO esperado)

Pasos en el iPhone:

1. Abrir IsyMotron Móvil → **Abrir GUS · asistente**.
2. Seleccionar **Proveedor remoto** → **Usar preset NVIDIA NIM**.
3. Guardar URL/modelo y API key (per por el diálogo nativo).
4. Enviar prompt corto (p. ej. "Di 'hola' y nada más").
5. Capturar: respuesta del modelo, hora, pantallas relevantes.

Negativos obligatorios en la misma sesión:

- **Sin elegir remoto**: enviar un mensaje en modo local/remoto sin configurar → no se hace request remoto.
- **Error NIM visible**: con key inválida/aislada (o sin red), el error HTTP se muestra como error; **no** cambia a local solo.
- **Regreso explícito**: volver a "En este teléfono" requiere acción del usuario.
- **Sin leaks**: las capturas no muestran la API key; ningún log la incluye.

## Evidence esperado

- `screenshots/` (owner): pantalla del preset NIM, error visible, respuesta real.
- `notes.md` (owner): fecha/hora, latencia percibida, errores, veredicto.
- `hashes.json`: SHA-256 de las capturas cuando existan.
- Símbolo de timestamp del teléfono + notas del modelo solicitado.

## Verdict template

| Claim | Verdict |
|---|---|
| GUS remoto explícito con preset NIM | NOT_DEMONSTRATED / DEMONSTRATED |
| Round trip real desde iPhone físico | NOT_DEMONSTRATED / DEMONSTRATED |
| Error NIM visible, sin fallback | NOT_DEMONSTRATED / DEMONSTRATED |
| Sin fuga de API key | NOT_DEMONSTRATED / DEMONSTRATED |
| Local GGUF en iPhone | NOT_DEMONSTRATED (fuera de alcance) |
