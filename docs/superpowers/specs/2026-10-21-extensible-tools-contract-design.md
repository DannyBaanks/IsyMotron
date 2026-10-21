# Tools extensibles por contrato — diseño de IsyMotron

Fecha: 2026-10-21. Estado: aprobado por el usuario el 2026-10-21; implementación autorizada en esta sesión.

## Intención y decisiones del usuario

La prioridad del cierre es que IsyMotron admita **tools nuevas con código propio**, no solo una lista fija de acciones como abrir Chrome. Nemotron debe preparar el paquete y sus requisitos de seguridad antes de que pueda ejecutarse. El usuario eligió **aprobar inicialmente cada tool y después reutilizarla dentro del alcance autorizado**. La meta es extensibilidad con un contrato común y verificaciones concretas, sin convertir el proyecto en una investigación de aislamiento universal.

Se conserva PC + iPhone 12 como flujo principal; la web muestra estado y evidencia. Esta extensión vive en la PC, separada de GUS móvil, cuyo rol permanece de orientación.

## Diseño elegido

Se consideraron dos vías: componer solamente capabilities existentes o admitir código nuevo con contrato y un proveedor de ejecución. El usuario eligió la segunda. El diseño incorpora una interfaz de proveedores para que agregar un nuevo tipo de integración no obligue a reescribir la admisión ni la aprobación.

La unidad instalable es **un paquete de tool**. Nemotron genera su código, manifest, receta de controles y casos de prueba. El host valida y compila la receta mediante componentes conocidos y produce el informe. Los tests del modelo se conservan como aportes; no reemplazan los casos obligatorios ni el veredicto del host.

```text
Necesidad que el catálogo actual no resuelve
    → Nemotron propone código + contrato + receta de controles + pruebas
    → validación de formato y resolución de controles disponibles
    → verificación local del paquete y sus límites
    → aprobación inicial del usuario sobre ese paquete y ese alcance
    → catálogo extensible
    → cada invocación verifica contrato, aprobación y grants vigentes
    → proveedor ejecuta y el host emite resultado + recibo
```

## Paquete y contrato

Estructura propuesta:

```text
csv-cleaner/
  tool.json
  main.py
  security.json
  cases.json
```

`ToolContract/v1` declara:

- Identidad: `tool_id`, versión, descripción y entrada al código dentro del paquete.
- Entradas y salidas: esquemas tipados, con un subconjunto explícito de JSON Schema. Campos/constructores no soportados son un error de validación, no una omisión silenciosa.
- Efectos: qué recursos lógicos lee y qué artefactos produce; red o procesos externos solo si existe un proveedor que pueda aplicar ese contrato.
- Proveedor: identificador y versión del mecanismo de ejecución requerido.
- Límites: duración, tamaño de entradas, tamaño de salida y presupuesto de recursos que el proveedor realmente soporte.
- Evidencia: digests del código, contrato, receta y casos, junto con las versiones de verificador y proveedor.

El manifiesto no otorga permisos. Los recursos se vinculan a grants del host; las rutas físicas y credenciales no forman parte del prompt de construcción.

`security.json` es una receta declarativa de controles: recursos accesibles, permisos mínimos, parámetros permitidos, límites y condiciones de rechazo. Nemotron puede proponerla y corregirla. El host la compila a un `SecurityPlan` mediante controles disponibles. Para una primitiva nueva puede añadirse un proveedor revisado que implemente la misma interfaz; no se acepta ejecutar silenciosamente un control desconocido como si funcionara.

## Qué significa «construirle la seguridad»

Antes de habilitar una tool, el sistema produce cuatro piezas vinculadas:

1. **Contrato:** operaciones y datos esperados.
2. **Plan aplicable:** configuración concreta del proveedor, no solo promesas en texto.
3. **Verificación:** casos normales y negativos, con observaciones del host.
4. **Admisión:** aprobación del paquete exacto dentro de los límites elegidos por el usuario.

Nemotron puede iterar sobre su propuesta cuando recibe un rechazo estructurado. No edita el enforcer en ejecución, el registro de aprobaciones ni el informe de admisión. Esos componentes ejecutan el protocolo común.

## Primer proveedor y demo

El primer proveedor ejecuta **tools Python de procesamiento de datos** en Linux: recibe copias de entradas autorizadas y entrega artefactos en staging. Se aprovecha bubblewrap, ya instalado y cuyo arranque básico se probó en este entorno. No se instala una plataforma nueva para este primer caso. Windows/macOS pueden continuar con las capabilities existentes; la ejecución de este proveedor se anuncia solo donde esté disponible y verificado.

El proveedor comparte únicamente el runtime necesario, el paquete y las entradas seleccionadas. No monta el home, llaves ni el workspace completo. La red y los accesos externos se deshabilitan en el perfil inicial. Los límites no implementados por ese proveedor se rechazan. El resultado JSON y los artefactos se validan en el host antes de publicarlos bajo un grant vigente.

Para efectos externos posteriores —por ejemplo navegador, servicio o aplicación— se añade un proveedor/puente que aplique el mismo contrato y conserve sus propios límites. La v1 no necesita una excepción especial por cada nombre de tool.

Tool de demo: **limpiar un CSV y generar un informe JSON**, con lógica creada como código del paquete. Solo recibe el CSV autorizado y produce el informe en el destino elegido. Una segunda tool de transformación distinta se instala por el mismo registro, demostrando que el núcleo no depende de la lógica de CSV.

## Estados y aprobación

Estados: `DRAFT → VERIFIED_FOR_SCOPE → AWAITING_APPROVAL → ACTIVE`; también `REJECTED`, `STALE` y `REVOKED`.

- El informe verificado especifica qué se comprobó y en qué entorno. No declara seguridad universal.
- La aprobación vincula el paquete completo, el plan de controles, versiones de proveedor/verificador, usuario, host y alcance autorizado.
- Cambiar código, contrato, receta, límites o dependencias invalida esa aprobación y exige volver a verificar. Una actualización del proveedor relevante invalida el caché de verificación.
- Revocar la aprobación impide nuevas invocaciones. Se cancelan trabajos activos cuando el proveedor lo soporte y se registra el resultado de la cancelación.
- Las invocaciones posteriores no repiten la aprobación de admisión, pero siguen comprobando grants, lease, parámetros, digests y límites de cada operación. Los perfiles de aprobación existentes conservan sus propias decisiones por operación.
- Un error o resultado desconocido no activa una tool. Un paquete rechazado puede guardarse para corregirlo, sin aparecer como ejecutable.

## Integración con el código actual

Se reutilizan los conceptos de `ActivityManifest`, `DoctorReport`, digests y registro por contenido, manteniendo compatibilidad con v0. Se agrega una capa de admisión y ejecución por contrato; no se interpreta `GitActivityRegistry.install()` como aprobación automática. Hoy ese método publica también informes DENY, algo válido para distribución de evidencia pero insuficiente para habilitar una tool.

El catálogo entrega al planner únicamente las tools activas y autorizadas. El constructor es un rol separado: puede ver un pedido para crear una tool, pero no ejecuta su propuesta. El uso normal conserva el rechazo de capabilities inexistentes del planner actual.

Se expone por CLI un flujo explícito de propuesta, verificación, aprobación, listado, ejecución y revocación. La UI reutiliza esos estados y muestra el resumen de contrato para la aprobación; el token/grant real permanece en el host.

## Criterios de aceptación del primer corte

- Agregar dos paquetes con código diferente sin editar la lógica ni la tabla de tools del host.
- Paquete incompleto o contrato inválido: rechazo estructurado antes de ejecutar su código.
- Tool sin informe vigente o sin aprobación inicial: no ejecutable, incluso con perfil `full`.
- Tool aprobada: opera solo sobre los datos y destinos autorizados; una ejecución genera recibo vinculado al paquete y al plan.
- Rechazar o contener la variante que intenta leer un canario fuera de las entradas, escribir fuera de staging o acceder a red no declarada; el informe no la habilita.
- Schema de salida inválido, timeout o exceso de salida: no publicar artefactos como éxito.
- Cambiar un byte después de la aprobación: estado `STALE` y bloqueo; el worker usa el snapshot verificado, no una ruta editable seleccionada por la tool.
- Aprobación inicial reutilizable dentro del alcance; revocación y grants vencidos impiden nuevas llamadas.
- Un proveedor ausente o incompatible produce estado no disponible, sin fallback a ejecución directa.
- Un fixture de Nemotron genera un paquete verificable; una corrida real con el proveedor configurado demuestra la propuesta de código antes de la demo.

## Evidencia de exploración

- `python -m pytest tests/test_doctor.py tests/test_marketplace.py tests/test_sandbox.py -q`: **16 pasan**.
- El sandbox Python actual declara expresamente que no es una frontera de seguridad del SO. Una prueba controlada con un archivo canario sintético confirmó que una lectura exterior no se registra y puede terminar con `PASS_FOR_SCOPE` si la escritura declarada coincide. Por ello no se usa ese resultado v0 como admisión suficiente para código nuevo.
- `bwrap --version`: **0.9.0**; una comprobación de arranque con namespaces y comando conocido terminó con exit 0. Esto confirma disponibilidad básica, no los criterios del proveedor aún pendiente.
- [Documentación oficial de Python](https://docs.python.org/3/library/sys.html#sys.addaudithook): los audit hooks no son adecuados para implementar un sandbox.
- [Proyecto bubblewrap](https://github.com/containers/bubblewrap): el llamador define la política; el binario es una pieza del proveedor, no una política completa.

## Prioridad en el roadmap

Este flujo pasa a ser la demostración principal de extensibilidad, junto con la PC y el móvil. La interfaz web se mantiene como monitor; se limita el pulido visual y la experimentación con nuevos modelos para reservar trabajo al contrato, la admisión, el proveedor y una demo real con código nuevo.

La implementación se divide en tres entregables revisables: (1) contrato + registro + aprobación, (2) proveedor + pruebas negativas + recibos, (3) constructor Nemotron + catálogo + integración móvil/CLI. Los arreglos de privacidad y de evidencia del panel continúan siendo necesarios para presentar correctamente esos resultados.
