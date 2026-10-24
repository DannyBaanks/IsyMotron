# Prueba de varias tools y dos vías de autoría

Fecha: 21 de octubre de 2026. Base del núcleo: commit `2f11be0`.

## Resultado

Se verificaron **6 paquetes** mediante el mismo registro y proveedor Linux. Cada uno se ejecutó dos veces, con recibos válidos: **12 ejecuciones correctas**. El núcleo no cambió. `lifecycle-results.json` contiene los digests, verificaciones y resultados completos.

| Tool | Vía probada | Resultado |
| --- | --- | --- |
| `word-count` | Paquete de referencia existente | Verificada y ejecutada |
| `csv-cleaner` | Paquete de referencia existente | Verificada y ejecutada |
| `json-prettifier` | Nuevo paquete de referencia escrito directamente | Verificada; artefacto publicado comprobado |
| `invoice-total` | Ejemplo de autoría personal, código escrito directamente | Verificada y ejecutada |
| `slugify-text` | Generada por Nemotron | Verificada y ejecutada; 3 casos adicionales |
| `csv-column-sum` | Generada por Nemotron | Verificada y ejecutada; 2 casos adicionales |

Los ejemplos escritos directamente fueron preparados por Codex para simular un desarrollador y un autor particular; no se atribuyen a personas externas. Las etiquetas de origen están en la evidencia, no son identidades autenticadas de publicadores ni privilegios del registro.

## Generación real

Modelo NVIDIA NIM: `nvidia/nemotron-3.5-lightning-30b-a3b`. Se pidieron tres tools nuevas, con un máximo de dos intentos por tool:

- `slugify-text`: primer intento rechazado por JSON inválido; segundo intento pasó el contrato, las pruebas del host y tres casos independientes.
- `csv-column-sum`: pasó al primer intento, incluidos dos casos independientes.
- `json-key-inspector`: ambos intentos rechazados por contrato inválido (esquema incompleto y fixtures que no coinciden con las lecturas). No se publicó ni aprobó ese paquete.

Son **2 de 3 solicitudes aceptadas** y **2 de 5 llamadas aceptadas**. No se ocultan los fallos ni se afirma fiabilidad del 100 %. La IA todavía necesita validación y, a veces, corrección. El reintento con diagnóstico lo coordinó el ejecutor de la prueba; el producto sigue generando una propuesta por invocación.

`generation-results.json` conserva todos los resultados. `generation-requests.json` conserva las instrucciones y casos independientes. Los paquetes aceptados están en `generated/`. No se editó su código después de generarlos.

Las llamadas usaron solo instrucciones y datos sintéticos. La clave existente se cargó desde el almacén privado sin imprimirla ni modificarla. No se guardaron trazas de razonamiento.

## Verificación de las dos vías

Los paquetes de referencia y el ejemplo personal usan exactamente `ToolPackage`, `ToolRegistry` y `linux-python/v1`. La prueba no instaló adaptadores específicos por tool ni modificó el núcleo para descubrirlas. Los fingerprints antes y después fueron iguales.

Cada paquete pasó las pruebas de frontera del host y sus casos aportados. Además se comprobó:

- Antes de aprobar, la ejecución queda bloqueada en `AWAITING_APPROVAL`.
- La misma aprobación permite dos ejecuciones dentro del alcance de prueba.
- Otro usuario no puede ejecutarla y ve un catálogo vacío.
- Un root no autorizado se rechaza con `OUT_OF_SCOPE`.
- Añadir una etiqueta `verified=true` al contrato no sustituye una verificación: el paquete se rechaza.
- Un paquete personal que declara no usar red pero llama a `socket.socket()` es rechazado durante la verificación y queda `REJECTED`.
- Revocar una tool bloquea la siguiente ejecución.
- Modificar el código de la tool personal crea un nuevo digest y devuelve su estado a `DRAFT`; no reutiliza la aprobación anterior.

Todas las aprobaciones fueron exclusivamente del ejecutor de prueba, sobre directorios temporales con datos sintéticos y un sujeto de prueba. El registro temporal se eliminó. No se aprobaron tools ni se modificaron directorios en el registro personal.

## Repetir sin llamadas a IA

Desde la raíz del worktree:

```bash
python evidence/TOOLS_MULTI_AUTHOR/verify_offline.py /tmp/isymotron-tools-recheck.json
```

Este comando revalida los paquetes guardados y repite las ejecuciones y controles en un registro temporal. Requiere Linux, bubblewrap y seccomp. No carga claves ni llama a NVIDIA. Los casos de generación fallida quedan registrados como evidencia y no se reinterpretan como paquetes válidos.

## Uso en el producto

Las dos vías ya pueden usarse por CLI:

1. Elegir un paquete existente de `examples/tools/`, o escribir una carpeta propia con los mismos cuatro archivos.
2. Preparar con `tool stage <carpeta>` y verificar con `tool verify <id>`.
3. Revisar y aprobar el alcance; ejecutar o dejar que el planner use el catálogo autorizado.

`examples/tools/README.md` explica cómo escribir un paquete sin IA. La procedencia no crea permisos. Un desarrollador puede distribuir una revisión revisada, pero el host vuelve a comprobarla en su entorno y el usuario decide su alcance.

Esta prueba no implementa una tienda, identidades firmadas de publicadores ni pantallas separadas de catálogo y tools personales. La selección visible en web/móvil sigue siendo trabajo de interfaz pendiente. El proveedor actual es para procesamiento local de datos en Linux; no habilita control de navegador ni red externa.


## Validación del repositorio

La nueva regresión `tests/test_tool_examples.py` se ejecutó primero sin el paquete y falló; tras añadir el paquete pasó, verificando la ejecución real y el artefacto declarado.

La primera suite completa terminó con **625 passed, 4 failed, 15 skipped**, 262.39 s. Fallaron estas pruebas existentes:

- `test_isymotron_cli.py::test_menu_ctrl_c_aborts_with_130`: timeout de 5 s del subproceso.
- `test_process_identity.py::test_scenario_X_execve_keeps_instance_and_changes_artifact`: observó `INSTANCE_MISMATCH` en lugar de `ARTIFACT_DRIFT`.
- `test_sandbox.py::test_outside_write_is_blocked_and_denied`: timeout del worker.
- `test_tool_registry.py::test_only_approved_input_snapshots_and_destinations_are_used`: timeout de una prueba de frontera.

Al finalizar se observó carga media de 30.31 en una máquina con 12 procesadores lógicos. La carga es una explicación posible; no se estableció causalidad para cada fallo. Las cuatro pruebas pasaron inmediatamente al repetirlas de forma aislada: **4 passed en 2.79 s**, sin modificar código ni límites. Se conserva `pytest-initial.txt` y `pytest-failures-recheck.txt`.

La revisión independiente de los nuevos paquetes, el ejecutor y la exactitud de los resultados no encontró hallazgos accionables.

La repetición completa, sin cambios al núcleo ni a los límites, terminó con **629 passed, 15 skipped**, 75.18 s. Ver `pytest-final.txt`. Los fallos iniciales se conservan en la evidencia; la repetición verde no convierte sus causas en un diagnóstico confirmado.
