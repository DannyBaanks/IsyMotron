# Paquetes de referencia

Estas tools vienen escritas en el repositorio y sirven como catálogo inicial para desarrolladores. Cada carpeta contiene código, contrato, controles y casos. Antes de habilitar un paquete, el host lo verifica con su proveedor actual y el usuario aprueba el alcance. Que un paquete aparezca aquí no crea permisos ni garantiza seguridad universal.

| Tool | Uso | Archivos declarados |
| --- | --- | --- |
| `word-count` | Cuenta palabras y caracteres de un texto | Ninguno |
| `csv-cleaner` | Limpia espacios en columnas y valores CSV | Lee `data.csv`; escribe `report.json` |
| `json-prettifier` | Ordena y formatea un objeto JSON | Lee `data.json`; escribe `pretty.json` |

El reporte de la prueba conjunta está en `evidence/TOOLS_MULTI_AUTHOR/RUN.md`. Sus resultados corresponden a los digests y al proveedor registrados allí; no constituyen una certificación de cualquier revisión futura.

## Usar un paquete existente

```bash
python tools/isymotron_cli.py tool stage examples/tools/json-prettifier
python tools/isymotron_cli.py tool verify json-prettifier
python tools/isymotron_cli.py tool list
```

La tool queda esperando aprobación. Revisa el código, los efectos y los directorios físicos antes de concederlos. Consulta `docs/EXTENSIBLE_TOOLS.md` para aprobar, ejecutar y revocar.

## Escribir una tool propia

No se necesita un modelo de IA. Puedes copiar `word-count` como plantilla y editar sus cuatro archivos:

- `main.py`: implementa `run(inputs)` usando Python estándar; devuelve el resultado sin imprimirlo.
- `tool.json`: identificador, versión, resumen, esquemas de entrada/salida y efectos de lectura/escritura.
- `security.json`: controles admitidos por el proveedor.
- `cases.json`: entradas, archivos sintéticos y resultados esperados.

Los archivos de entrada se leen desde `/inputs/<nombre>`. Solo se escriben los artefactos declarados en el directorio de trabajo. No hay red ni procesos externos en este primer proveedor.

El ejemplo `evidence/TOOLS_MULTI_AUTHOR/custom/invoice-total/` muestra una tool personal con código escrito directamente: suma importes en centavos enteros. Pasa por los mismos comandos `stage`, `verify` y `approve` que un paquete del catálogo o generado por IA. No hay que registrarla en una lista del núcleo ni modificar el planner.

La verificación de un paquete no activa otro paquete ni una revisión modificada. Cambiar código o contrato exige volver a verificar y aprobar. Una aprobación vigente puede reutilizarse dentro de su alcance hasta que expire o se revoque.
