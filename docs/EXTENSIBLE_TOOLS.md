# Tools extensibles por contrato

Una tool agrega código propio al catálogo de IsyMotron sin añadir una rama de ejecución por cada nombre de tool. Nemotron puede construir su paquete; el host verifica y aplica su contrato. La aprobación inicial del usuario habilita una revisión concreta para un sujeto, host, alcance y periodo.

La primera implementación usa Python estándar y bubblewrap en Linux. Requiere el Python de sistema, bibliotecas dinámicas del sistema y `libseccomp.so.2`. Un proveedor ausente falla cerrado. No instala dependencias ni cambia al sandbox Python v0 como fallback. Las capabilities de escritorio existentes conservan su funcionamiento.

## Prueba completa

Desde la raíz del checkout:

```bash
python tools/isymotron_cli.py tool demo
```

La demo ejecuta los dos paquetes incluidos (`csv-cleaner`, `word-count`) en un directorio temporal, verifica, aprueba, ejecuta, comprueba el artefacto CSV/JSON y prueba revocación. Solo la demo concede sus propios recursos temporales; no añade aprobaciones al registro normal ni llama a un proveedor de IA.

## Paquete

```text
my-tool/
  tool.json
  security.json
  cases.json
  main.py
```

`main.py` define `run(inputs)` y devuelve un valor JSON que cumple `output_schema`. Lee los archivos declarados desde `/inputs/<nombre>` y escribe los artefactos declarados bajo el directorio de trabajo. Los archivos de salida ya existen: se abren y se escriben directamente; no hay scratch, creación de directorios, `tempfile`, unlink ni renombrado atómico dentro del worker. No imprime mensajes al stdout; ese canal está reservado al resultado JSON.

El contrato completo está en [el ejemplo CSV](../examples/tools/csv-cleaner/tool.json); los [controles](../examples/tools/csv-cleaner/security.json), [casos](../examples/tools/csv-cleaner/cases.json) y [código](../examples/tools/csv-cleaner/main.py) son independientes y forman parte del digest del paquete.

Los esquemas admiten `type` y `enum`; objetos con `properties`, `required` y `additionalProperties: false`; arrays con `items` y `maxItems`; strings con `minLength`/`maxLength`; números con `minimum`/`maximum`. No admiten `$ref`, expresiones regulares, composición ni claves desconocidas. Las entradas al Host son objetos. El esquema se valida antes de ejecutar y después de recibir resultados.

Límites de `ToolSecurity/v1`: timeout entero de 1–30 segundos, memoria virtual 32–1024 MiB, entradas hasta 16 MiB y salida combinada JSON/artefactos hasta 1 MiB. Red y procesos externos deben ser `false` en este proveedor. El presupuesto de salida combinada se comprueba antes de publicar. Durante la ejecución, cada archivo está limitado a ese presupuesto y solo existen hasta 32 archivos de artefactos escribibles; por ello el staging vivo ocupa como máximo `número_de_artefactos × max_output_bytes`, más stdout/stderr limitados individualmente. No se pueden crear archivos ni directorios adicionales en `/work`, `/tmp` o `/dev`. Los tamaños menores especificados por una tool también se aplican. El paquete tiene como máximo 64 archivos y 2 MiB, sin enlaces simbólicos ni hardlinks.

## Proponer con Nemotron

Usa la configuración existente del planner (`ISYMOTRON_PROVIDER`, `ISYMOTRON_MODEL` y su credencial, cuando corresponda):

```bash
python tools/isymotron_cli.py tool propose "Limpia un CSV y produce un informe JSON" --destination /tmp/my-tool-proposal
```

Esto solo escribe una propuesta validada e inerte. No verifica ejecutando código, no modifica el registro y no aprueba nada. Una respuesta truncada o inválida no publica un paquete parcial. El constructor recibe la intención y el formato del contrato; no recibe grants, rutas físicas, resultados de otras tools ni credenciales.

## Verificar y aprobar

El registro por defecto está en `~/.isymotron/tools`; se puede elegir con `--registry` o `ISYMOTRON_TOOLS_DIR`. Evita poner este registro en un repositorio, directorio público o carpeta sincronizada con terceros: contiene autoridad local. La clave del registro es local, independiente de la del proveedor de IA, y no se copia al worker.

```bash
python tools/isymotron_cli.py tool stage examples/tools/csv-cleaner
python tools/isymotron_cli.py tool verify csv-cleaner
python tools/isymotron_cli.py tool list
```

Revisa el contrato, el informe y los directorios que vas a conceder. Los directorios deben existir. Por ejemplo, si preparaste `/tmp/tool-input` y `/tmp/tool-output`:

```bash
python tools/isymotron_cli.py tool approve csv-cleaner --read-root in=/tmp/tool-input --write-root out=/tmp/tool-output --ttl 3600 --yes
python tools/isymotron_cli.py tool run csv-cleaner --inputs '{}' --file data.csv=hostfs://in/data.csv --output hostfs://out
python tools/isymotron_cli.py tool revoke csv-cleaner
```

`--yes` es la decisión local explícita sobre el paquete y los roots revisados. El contrato no crea esos permisos por sí mismo. La aprobación dura una hora por defecto y como máximo 24 horas; la expiración y la revocación se comprueban en cada llamada y antes de publicar salidas. Cambiar código, controles, casos o proveedor invalida el paquete aprobado. En v1 hay una aprobación activa por tool; aprobarla para otro sujeto reemplaza la anterior.

Las lecturas se copian usando descriptores relativos a roots autorizados y sin seguir symlinks. El worker recibe esas copias, no el árbol original. Las salidas se comprueban antes de copiar al destino; cada archivo se publica por reemplazo atómico. Una invocación con varios artefactos no promete una transacción entre todos los archivos si falla el almacenamiento durante la publicación.

## Catálogo, consola y móvil

```bash
export ISYMOTRON_TOOLS_DIR=/ruta/al/registro
python tools/isymotron_cli.py console
```

La consola agrega un host `tools-local`. El planner ve únicamente las tools activas aprobadas para `console:local` y ese host, como capabilities `tools.csv-cleaner`. Una lease también se vincula al digest de esa revisión: una lease anterior no permite ejecutar una actualización.

El task runner agrega el mismo host por tarea, usando la identidad exacta `link:mobile:<office_id>` del remitente. Para una tool móvil, el dueño la aprueba con esa identidad:

```bash
python tools/isymotron_cli.py tool --subject link:mobile:OFFICE_ID approve csv-cleaner --read-root in=/tmp/tool-input --write-root out=/tmp/tool-output --yes
python tools/isymotron_cli.py task-runner --watch 2
```

La tarea llega por el flujo Link existente y el planner decide cómo usar el catálogo. GUS del teléfono sigue sin herramientas propias. El alta/aprobación/revocación se realizan por la CLI local en este primer corte; no se añadió una pantalla móvil de creación de paquetes.

## Verificación y recibos

El host ejecuta sus propias pruebas de frontera, además de los casos aportados por el paquete. Un caso aportado no puede producir el informe de autoridad. El reporte describe `PASS_FOR_SCOPE` en ese proveedor; no prueba exactitud funcional para todas las entradas ni seguridad universal.

El registro firma sus registros y recibos con HMAC local y vincula paquete, plan y versiones. No acepta el `DoctorReport` v0 ni una etiqueta emitida por el propio código como aprobación. El resultado de una tool es dato no confiable: nunca modifica la aprobación ni el registro.

Esta v1 ejecuta procesamiento local de datos, no control de navegador ni red externa. Añadir otro tipo de integración requiere registrar un proveedor revisado que compile y aplique los controles de su contrato. El registro, el constructor y el ciclo de aprobación son comunes.

## Checks

```bash
python -m pytest tests/test_tool_contract.py tests/test_tool_provider.py tests/test_tool_registry.py tests/test_tool_builder.py tests/test_tool_cli.py -q
python -m pytest -q -rs
```

Las pruebas de worker real necesitan Linux/bubblewrap; otras plataformas las omiten explícitamente. El constructor se prueba también con una respuesta determinista del proveedor para separar el protocolo de generación del acceso a un servicio real.


## Pruebas reales con NVIDIA (21 de octubre)

La clave NIM existente permite llamar al servicio sin cambiar el proveedor guardado. `nemotron-3.5-embed-1b` se probó para recuperar descripciones de tools: es un modelo de embeddings y no sirve como constructor de código. La prueba exploratoria y sus límites están en `evidence/NVIDIA_NEMOTRON_1B/`.

Una tool generada con `nvidia/nemotron-3.5-lightning-30b-a3b` pasó la verificación real del host y dos casos adicionales. El constructor ahora pide metadatos como objetos/arrays JSON y deja su serialización al host; el código sigue siendo texto y todo el paquete conserva las mismas verificaciones. Para ese modelo exacto se solicita respuesta directa con `enable_thinking=false`. Las propuestas anteriores con metadatos en strings siguen soportadas.

La primera propuesta válida falló por leer desde una ruta relativa; una nueva propuesta del modelo, con ese diagnóstico, corrigió la ruta. Ese ciclo fue coordinado por Codex: el producto todavía genera una propuesta por petición y verifica por separado. No habilita tools automáticamente. La revisión está en `evidence/NVIDIA_NEMOTRON_GENERATION/verified-proposal/`, sin aprobación para el registro personal. Ver `evidence/NVIDIA_NEMOTRON_GENERATION/RUN.md` para resultados y límites.
