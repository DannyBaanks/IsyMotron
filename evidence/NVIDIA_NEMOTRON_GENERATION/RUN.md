# Generación real de tools con Nemotron — 21 de octubre de 2026

## Resultado actual

**Una tool generada por NVIDIA NIM pasó el contrato y la verificación independiente del host.** Modelo: `nvidia/nemotron-3.5-lightning-30b-a3b`. Paquete: `verified-proposal/`, tool `contact-email-extractor`.

Digest: `sha256:f1c54a7271ce9f8338d14af08520d5b04bb2de5f9cd8aa67505dda4ed443e49c`.

`verified-result.json` registra:

- `PASS_FOR_SCOPE` del proveedor Linux y del registro.
- Pruebas del host que bloquean escritura fuera del alcance, red y creación de procesos.
- El caso del paquete y dos casos independientes: duplicados adicionales y archivo vacío.
- Intentar ejecutar desde el registro sin aprobación terminó en `AWAITING_APPROVAL`.

El código y su contrato fueron escritos por el modelo. Codex revisó el código y ejecutó las verificaciones; no editó la fuente generada. La aprobación está pendiente. El registro usado para verificar fue temporal y se eliminó. No se habilitó esta tool en el registro personal del usuario.

## Causa y solución

El protocolo anterior pedía JSON serializado dentro de strings JSON. Una respuesta real tenía un sobre exterior válido, pero `cases.json` contenía un objeto `inputs` mal escapado. Ver `diagnosis-before-fix.json`. También faltaba `properties` en el esquema de entrada vacío.

Ahora el constructor solicita `tool.json` y `security.json` como objetos y `cases.json` como array dentro de `files`. El host serializa esos tres metadatos; las fuentes siguen siendo strings. La validación completa de `ToolPackage` se aplica después. Los paquetes anteriores con strings continúan soportados y no se reparan silenciosamente si están rotos. Los errores identifican fallos de formato/contrato sin copiar el texto del modelo a la salida.

Un intento con el presupuesto de razonamiento de 1024 aún se truncó al consumir 8192 tokens. Para este modelo exacto, el constructor solicita `chat_template_kwargs.enable_thinking=false`. Otros modelos mantienen su protocolo.

## Evidencia de los intentos

| Paso | Resultado | Tiempo |
| --- | --- | --- |
| Diagnóstico con protocolo anterior | Rechazado: metadatos JSON inválidos | 41.927 s |
| Metadatos estructurados, límite de razonamiento | Rechazado: respuesta truncada | 66.368 s |
| Metadatos estructurados, respuesta directa | Paquete válido; verificación rechazó lectura relativa | 5.100 s |
| Nueva propuesta con feedback de verificación | Paquete válido y `PASS_FOR_SCOPE` | 2.978 s de generación |

La primera propuesta válida leía `contacts.txt` desde `/work`, pero los archivos autorizados están en `/inputs`. El worker la rechazó. Codex envió ese diagnóstico en una nueva petición y el modelo generó una revisión que usa `/inputs/contacts.txt`. Ver `diagnosis-relative-read.json` y `verified-result.json`.

Este ciclo de corrección fue coordinado por Codex. **El producto todavía no implementa reintentos autónomos con feedback de verificación.** `tool propose` sigue generando una sola propuesta inerte; `tool verify` es un paso separado.

Los tiempos corresponden a estas llamadas, no son un benchmark de rendimiento o confiabilidad. Los archivos `live-result.json` y el reporte `pytest.txt` conservan el intento y la validación del corte anterior.

## Revisar y verificar localmente

Desde la raíz del worktree:

```bash
python tools/isymotron_cli.py tool --registry /tmp/isymotron-review-generated stage evidence/NVIDIA_NEMOTRON_GENERATION/verified-proposal
python tools/isymotron_cli.py tool --registry /tmp/isymotron-review-generated verify contact-email-extractor
```

Esto prepara y verifica el paquete, sin aprobar su uso. La aprobación requiere elegir explícitamente un directorio de lectura autorizado. El paquete declara solo `contacts.txt`, ninguna escritura, red deshabilitada y procesos externos deshabilitados.

## Alcance

Se usaron únicamente instrucciones y contactos sintéticos de `example.com`; no se enviaron archivos del usuario. La clave NIM existente se cargó en memoria desde el almacén privado sin imprimirla, modificarla o guardarla en evidencia. No se guardaron trazas de razonamiento.

El extractor usa una expresión regular sencilla: los casos aprobados no demuestran validación completa de direcciones de correo ni exactitud universal. La verificación se hizo en Linux con bubblewrap/seccomp. No prueba ejecución en iPhone, macOS o Windows.

## Referencias

- API: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer
- Parámetro de respuesta directa: https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b

## Validación del cambio final

- Pruebas enfocadas del constructor/proveedor: `30 passed`.
- Suite completa: `628 passed, 15 skipped`, 74.26 s. Ver `pytest-verified-generation.txt` para las omisiones.
- Revisión independiente del diff: sin hallazgos accionables; incluyó el formato estructurado y el control opcional de respuesta directa.
- Se comprobó primero que las regresiones nuevas fallaban con el código anterior, y después que pasaban con el cambio.

Las pruebas deterministas no sustituyen las llamadas reales ni las pruebas de worker descritas arriba.
