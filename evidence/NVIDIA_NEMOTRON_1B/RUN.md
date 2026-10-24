# Nemotron 3.5 Embed 1B — prueba exploratoria

El modelo `nvidia/nemotron-3.5-embed-1b` se probó en NVIDIA NIM con una consulta en español y cinco descripciones sintéticas de tools. La tool esperada, `csv-cleaner`, quedó primera por similitud coseno (0.649778; siguiente 0.148360). Los vectores tuvieron 2048 dimensiones.

Los números están en `embedding-retrieval.json`. Es una consulta exploratoria: no demuestra calidad general, selección segura de permisos ni funcionamiento local en iPhone. No se integró aún un selector semántico en producción. El resultado sugiere una utilidad futura para recuperar tools candidatas; su ejecución sigue dependiendo del contrato y de la aprobación vigente.

Este modelo genera embeddings, no paquetes de código ni respuestas de chat. Para generación se probó por separado Lightning 30B; ver `../NVIDIA_NEMOTRON_GENERATION/RUN.md`.

La clave se cargó desde el almacén privado existente sin imprimirla ni cambiarla. No se enviaron archivos del usuario.

Referencia oficial: https://build.nvidia.com/nvidia/nemotron-3_5-embed-1b
