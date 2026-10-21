# Prueba de generación real — 21 de octubre de 2026

Proveedor: NVIDIA NIM; modelo: `nvidia/nemotron-3.5-lightning-30b-a3b`.

## Resultado

**La generación real todavía no pasa el contrato.** El intento final del constructor modificado devolvió `INVALID_PROPOSAL` en 10.171 s. No se publicó una propuesta, no se ejecutó código generado ni se creó una aprobación. Ver `live-result.json`.

El pedido usó únicamente texto sintético: un extractor de correos de `contacts.txt`, con casos de `example.com`. No se enviaron archivos del usuario. La clave existente se cargó en memoria desde el almacén privado; no se imprimió, modificó ni guardó en evidencia.

## Hallazgos y cambio

Un intento previo consumió sus 8192 tokens sin respuesta final (`finish_reason=length`, contenido vacío, 72.397 s). La API documenta un presupuesto de razonamiento predeterminado de 16384 tokens. El constructor ahora limita ese presupuesto a 1024 para este modelo concreto, manteniendo 8192 tokens de salida total, y aporta un ejemplo válido del paquete completo. En proveedores locales solicita también el modo JSON ya soportado. Los demás modelos conservan su protocolo.

La respuesta final siguió sin ser un paquete admitido. Este archivo no atribuye la causa concreta a Markdown, sintaxis JSON o contenido del contrato: no se conservó la respuesta final para distinguirlos. No se guardaron trazas de razonamiento. La menor latencia observada no es una medición comparativa controlada.

## Qué falta

Capturar un diagnóstico estructural de la respuesta inválida (sin razonamiento ni credenciales), corregir su formato y obtener una propuesta que pase la verificación independiente del host. Después, revisar y aprobar su alcance antes de habilitarla para el usuario. Las pruebas deterministas y la demo de paquetes incluidos no sustituyen esta prueba real.

No se cambió el proveedor por defecto ni la configuración de claves.

## Referencias

- API y presupuesto: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer
- Ejemplo oficial: https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b

## Validación local del cambio

`python -m pytest tests/test_tool_builder.py tests/test_local_provider.py -q`: 23 passed.

`python -m pytest -q -rs`: **621 passed, 15 skipped**, 77.06 s. Ver `pytest.txt` para las omisiones. Esta suite no usa la clave NIM guardada ni demuestra generación real válida.

Se agregaron regresiones para rechazar propuestas truncadas, validar el ejemplo del constructor, reservar el presupuesto de respuesta en Lightning y rechazar presupuestos inválidos antes de enviar una petición.
