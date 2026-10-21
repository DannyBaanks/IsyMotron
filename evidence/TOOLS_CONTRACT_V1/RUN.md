# Extensible tools v1 — ejecución local

Fecha: 2026-10-21. Código probado: `3146b8623165cf661948042338b7d45ec67f52e1`.
Rama: `codex/extensible-tools-contract`; base: `c0bf8d5c10eb4727865abeeaa1f0ef8a7e24465b`.

## Resultado observado

- `python -m pytest -q -rs`: **618 passed, 15 skipped**, 82.08 s. Baseline: 573 passed, 15 skipped. [Log completo](pytest.txt).
- `python tools/isymotron_cli.py tool demo`: exit 0. Dos paquetes con código propio y un único protocolo: CSV con dos registros normalizados, conteo de «hola mundo» = 2 palabras/10 caracteres, y revocación aplicada. [Salida real](demo.json).
- La demo utiliza scopes temporales y una autoridad local temporal eliminada al terminar. Sus recibos conservan digests y sellos; verificar un HMAC exportado requiere la autoridad local original, que no se publica con esta evidencia.
- Integración de consola y ejecutor Link probada con el planner existente y un proveedor determinista. No se probó un iPhone físico en esta entrega.
- Generación real de Nemotron **no probada**: `Provider()` selecciona nebius / nvidia/nemotron-3-super-120b-a12b y `configured()` es false. El constructor y sus errores se probaron con respuestas deterministas; esto no demuestra calidad de generación del modelo real.

## Alcance

Código Python estándar en Linux; bubblewrap, Python de sistema y libseccomp. Constructor → paquete inerte → verificación del host → aprobación inicial → catálogo dinámico → llamadas con lease y recibo. Cambios de paquete/proveedor, revocación, sujeto/host incorrectos o expiración impiden nuevas ejecuciones.

No se publicaron releases ni despliegues; la rama aislada queda disponible. [Guía reproducible](../../docs/EXTENSIBLE_TOOLS.md).

## Revisión y decisiones

La revisión independiente encontró dos problemas importantes: seguir un ancestro reemplazado por symlink y consumir staging sin límite agregado durante la ejecución. Se reprodujeron y corrigieron con pruebas de regresión. La revisión posterior confirmó esas correcciones y encontró preasignación de disco mediante fallocate, también reproducida y denegada por el filtro del kernel. La denegación de ioctl usa EPERM para permitir que las comprobaciones normales isatty de Python continúen; usar TRAP inicialmente rompió las pruebas positivas y se corrigió antes del resultado final.

- **Worktree manual:** el repositorio IsyMotron está anidado y la herramienta de worktrees de la app apunta al padre sin selector de repositorio. Costo: este checkout no está administrado por la app.
- **Autoridad HMAC local:** clave privada independiente del proveedor IA, nunca añadida automáticamente a las entradas del worker. Costo: los recibos exportados requieren esa autoridad para comprobar el sello.
- **Una aprobación activa por tool:** sujeto, host, roots y expiración quedan vinculados; reaprobar para otro sujeto reemplaza la anterior. Costo: esta v1 no ofrece múltiples sujetos simultáneos por paquete.
- **Archivos de salida declarados y precreados:** directorios de trabajo y temporales readonly, sin crear archivos, mkdir, unlink o rename en el worker. Máximo 32 artefactos; cada archivo vivo está limitado por max_output_bytes y la salida publicada combinada debe cumplir ese presupuesto. Costo: una tool que necesita scratch requiere ampliar el contrato/proveedor, en vez de almacenamiento implícito sin límite. La publicación es atómica por archivo, sin transacción entre todos los artefactos.

No se afirma aislamiento universal ni exactitud funcional para todas las entradas. Los skips de modelos, otros sistemas operativos y repositorios externos se conservan del baseline.
