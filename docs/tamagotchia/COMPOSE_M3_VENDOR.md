# COMPOSE — TamagotchIA GUS Life
## M3.3–M3.4 — Reutilizar el runtime local de iSyCode Móvil mediante vendoring fijado y verificable

> Copia textual del Compose que entregó el usuario el 2026-09-30, decisión sobre M3.3/M3.4.
> Seguimiento en [`ROADMAP.md`](ROADMAP.md).

### Decisión

Para M3.3/M3.4 elegimos:

> COPIA FIJADA / VENDORED SNAPSHOT desde un commit explícito de iSyCode Móvil.

NO usar submódulo por ahora.

NO extraer todavía un paquete/repositorio independiente.

Esto NO significa duplicar manualmente infraestructura.

La copia debe:

- tener un upstream explícito;
- estar fijada a un commit exacto;
- poder regenerarse mediante un script;
- ser verificable por CI;
- detectar drift;
- conservar provenance;
- prohibir modificaciones silenciosas a la copia vendorizada.

La decisión se toma por ser el slice mínimo que permite reutilizar el runtime probado
sin introducir todavía una nueva frontera de distribución.

Si más adelante existen varios consumidores estables del mismo runtime,
se reevaluará su extracción a paquete/repositorio propio.

---

# 0. PISO ACTUAL

Según el handoff actual:

## TamagotchIA

M0: completo.

M1: completo.

Incluye:

- PetIdentity independiente de modelo/provider;
- LifeLog con provenance;
- ContextBudget;
- ContextBoxV1;
- save v2;
- `mode`;
- `rulesetVersion`;
- migración no destructiva;
- fixture v1 real;
- saves v1 migran siempre a `local`;
- original anterior se conserva para rollback.

M2: completo.

Incluye:

- Context Compiler puro;
- presupuesto;
- poda por prioridad;
- orden estable -> volátil;
- filtrado de credenciales.

M3:

- M3.1 `CreatureMind`: completo.
- M3.2 frontera Capacitor TS: completa y probada con fake plugin.
- M3.3/M3.4: detenidos esperando esta decisión.

Tests reportados:

    58 -> 99

Además:

    typecheck PASS
    build PASS

Verificar todo esto antes de apoyarse en ello.

## Seguridad actual

Hasta M5:

- cerebro LOCAL puede recibir ContextBox completo según contrato actual;
- cerebro REMOTO sigue recibiendo únicamente la proyección anterior/acotada;
- NO ampliar el egress remoto en este milestone.

Preservar esta frontera.

---

# 1. OBJETIVO

Conectar TamagotchIA con el runtime local ya probado de iSyCode Móvil
sin crear una segunda implementación de llama.cpp/GUS.

Queremos:

    TamagotchIA
        |
    CreatureMind
        |
    Native Local Mind Adapter
        |
    vendored GUS runtime
        |
      llama.cpp

La mascota sigue siendo propietaria de:

- identidad;
- memoria;
- contexto;
- estado;
- reglas.

El runtime únicamente proporciona inferencia.

No mover semántica de TamagotchIA hacia el bridge.

---

# 2. INSPECCIÓN OBLIGATORIA ANTES DE COPIAR

Inspeccionar el estado ACTUAL de iSyCode Móvil.

No confiar en paths recordados ni en el ZIP.

Determinar exactamente:

- commit de upstream que se usará;
- archivos C/C++ realmente necesarios;
- headers necesarios;
- dependencias;
- flags de compilación;
- llama.cpp dependency boundary;
- qué código es portable;
- qué código es específico de iOS;
- qué código es específico de Android;
- qué código pertenece a catálogo/UI/crash recorder y NO debe copiarse.

Revisar además el estado merged de:

- sampling anti-loop;
- no-think;
- UTF-8;
- chat templates;
- cualquier cambio posterior relevante al bridge.

Sólo después definir el snapshot.

No vendorizaremos por intuición.

---

# 3. ALCANCE DEL VENDOR

Copiar SOLAMENTE la capa mínima necesaria para inferencia local.

No copiar:

- UI de iSyCode Móvil;
- marketplace;
- catálogo completo salvo que el bridge requiera una pieza concreta;
- crash UI;
- navigation;
- app state;
- unrelated model management;
- authority de iSyCode Móvil;
- código ajeno al runtime requerido.

Objetivo:

> compartir motor, no compartir aplicación.

Si el bridge actual está demasiado acoplado para extraer un subset pequeño,
DETENER y documentar el acoplamiento antes de hacer un refactor grande.

---

# 4. PROVENANCE DEL SNAPSHOT

Crear un manifiesto equivalente a:

    upstream repo
    upstream commit SHA
    synced_at
    source paths
    destination paths
    file hashes
    optional patch set if absolutely necessary

No inventar el nombre/path final antes de inspeccionar convenciones del repo.

El manifiesto debe permitir responder:

> ¿exactamente de qué versión de iSyCode Móvil salió este runtime?

sin depender de memoria humana.

---

# 5. SCRIPT DE SYNC

Crear un script reproducible.

Responsabilidades:

    fetch/read upstream revision
    verify expected commit
    copy only allowlisted files
    normalize only what is necessary
    compute hashes
    update provenance manifest
    fail on unexpected source layout

No debe:

- hacer cambios fuera del vendor target;
- actualizar automáticamente a HEAD;
- elegir "latest";
- modificar el bridge upstream;
- ocultar diferencias.

El PIN se cambia explícitamente.

Ejemplo conceptual:

    sync_gus_runtime --from <SHA>

Pero inspeccionar tooling actual antes de decidir CLI/nombre.

---

# 6. NO MANUAL EDITS EN VENDOR

La carpeta vendorizada debe considerarse GENERATED/UPSTREAM SNAPSHOT.

Si TamagotchIA necesita comportamiento adicional:

NO editar silenciosamente el C vendorizado.

Preferir:

    adapter propio
    wrapper propio
    configuration
    capability del bridge upstream

Si aparece un bug real compartido:

1. corregir upstream en iSyCode Móvil;
2. verificarlo;
3. actualizar PIN;
4. resincronizar.

Queremos evitar dos forks invisibles del runtime.

---

# 7. CI — DRIFT CHECK

Agregar un check reproducible:

    checkout/read pinned upstream
    regenerate vendor snapshot in temp
    compare with committed snapshot

PASS:

    identical

FAIL:

    vendored runtime drifted from pinned upstream

También verificar hashes/provenance.

No depender sólo de:

    git diff

si eso deja huecos en generated metadata.

La intención es demostrar:

> lo committeado en TamagotchIA corresponde al upstream declarado.

---

# 8. CREATUREMIND SIGUE SIENDO LA FRONTERA

El código de juego NO debe conocer llama.cpp.

Debe seguir viendo algo equivalente a:

    CreatureMind.request(...)

o el contrato real existente.

Implementar un adapter:

    NativeLocalCreatureMind
          |
          v
    Capacitor native boundary
          |
          v
    platform native adapter
          |
          v
    vendored runtime

No dejar imports/FFI del bridge filtrándose hacia:

- engine;
- store;
- memory;
- ContextCompiler;
- Canon logic.

---

# 9. IOS

Inspeccionar cómo iSyCode Móvil compila/expone actualmente el bridge.

Reutilizar ese conocimiento.

No asumir que su wrapper Swift puede copiarse directamente.

TamagotchIA debe tener su integración propia alrededor del runtime común.

Demostrar como mínimo:

    plugin available
    model load path valid
    prompt/context crosses boundary
    UTF-8 preserved
    generated text returns
    errors map to typed failure
    cancellation/timeout behavior understood

No declarar "works on real iPhone"
hasta probarlo físicamente.

---

# 10. ANDROID

Misma regla.

Inspeccionar el JNI real de iSyCode Móvil.

Reusar el runtime compartido,
pero mantener el glue específico de TamagotchIA separado.

Verificar:

- UTF-8 bytes;
- lifecycle;
- model handle ownership;
- memory cleanup;
- failures;
- cancellation where supported.

No asumir paridad iOS/Android sin prueba.

---

# 11. SAMPLING

El runtime local de TamagotchIA debe beneficiarse
de las correcciones ya demostradas upstream cuando correspondan:

- anti-loop sampling;
- no accidental double accept;
- thinking-off directives where model metadata says so;
- template handling.

Pero mantener dos modos conceptualmente separados:

CHAT:
    sampling apropiado para interacción

BENCHMARK:
    deterministic/greedy when required

No mezclar benchmark behavior con creature chat.

---

# 12. STRUCTURED OUTPUT

M3.3/M3.4 NO debe convertirse en una reimplementación completa
de structured generation salvo que sea necesaria para conectar el runtime.

Primero lograr:

    ContextBox -> local model -> speech/result

Después se continúa con el milestone de grammar/schema
según ROADMAP.

Si el runtime ya expone grammar de forma limpia,
documentarlo para el siguiente slice.

No ampliar scope sin necesidad.

---

# 13. MODELOS

No hardcodear un único modelo.

El adapter recibe un model reference/path/config
según la arquitectura actual.

La identidad de la criatura jamás incluye:

    modelName
    providerName

como identidad esencial.

Cambiar el modelo debe conservar:

    PetIdentity
    LifeLog
    save
    memories
    Canon/Local mode
    ruleset
    relationships

---

# 14. FALLBACK

Si native local GUS:

- no está instalado;
- no encuentra modelo;
- falla load;
- queda sin RAM;
- devuelve error;
- excede tiempo;
- produce output inválido;

TamagotchIA NO deja de funcionar.

Debe caer a la estrategia existente permitida:

    local deterministic/fallback voice

o provider permitido por configuración/política.

Nunca hacer que adoptar una mascota dependa de llama.cpp.

---

# 15. CONTEXT SECURITY

Antes de cruzar el native boundary:

- validar ContextBox;
- verificar budget;
- filtrar secrets según contrato;
- no incluir API keys;
- no incluir grants;
- no incluir credentials;
- no incluir capability tokens.

El bridge de inferencia no necesita autoridad del juego.

Sólo texto/config/model runtime.

---

# 16. NO AUTHORITY EN EL BRIDGE

El bridge NO recibe acceso a:

- game engine mutation;
- Canon state mutation;
- inventory;
- filesystem arbitrario;
- shell;
- network;
- credentials.

Debe recibir inferencia y devolver inferencia.

Cadena:

    engine/context
        |
    projection
        |
    local mind
        |
    runtime
        |
    text
        |
    validator
        |
    game presentation

Nunca:

    runtime -> world mutation

---

# 17. TESTS DEL SYNC

Agregar pruebas para demostrar:

    pinned SHA is explicit
    source allowlist is explicit
    sync deterministic
    drift is detected
    unexpected upstream file/path fails
    manual vendor modification fails CI
    provenance hashes match

No fakear upstream en todos los tests
si existe una forma razonable de probar la lógica con fixtures.

CI network behavior debe ser considerado.

---

# 18. TESTS DEL ADAPTER

Agregar tests para:

    CreatureMind local path
    native plugin unavailable
    native error
    timeout
    malformed response
    UTF-8
    empty output
    ContextBox rejection
    fallback path

Mantener fake plugin para unit tests rápidos.

El runtime real debe tener smoke separado.

---

# 19. SMOKE NATIVO

Después de compilar integration:

usar al menos un modelo pequeño conocido
para smoke real del bridge.

Congelar:

- model identity;
- hash;
- context;
- generation config;
- expected invariant.

NO exigir texto literal si sampling no es determinista.

Sí exigir:

    process survives
    model loads
    output non-empty/valid
    UTF-8 valid
    no obvious control-token leak
    cleanup succeeds

---

# 20. RAM / KILL

No introducir claims de soporte por dispositivo sin evidencia.

Si un modelo no cabe:

    fail safely where possible

Pero recordar:

iOS puede matar la app.

El save debe estar seguro antes de cargar/generar.

No guardar prompts privados en crash reports.

Si reutilizar crash diagnostics upstream es útil,
hacerlo en milestone separado salvo que sea requisito directo.

---

# 21. ACTUALIZACIÓN DEL PIN

Documentar proceso explícito:

    upstream change merged
       |
    review
       |
    choose new SHA
       |
    sync
       |
    inspect diff
       |
    smoke/tests
       |
    commit PIN update

Nunca:

    auto-follow-main

Queremos actualizaciones conscientes.

---

# 22. CRITERIO PARA EXTRAER PAQUETE FUTURO

No hacerlo ahora.

Crear una nota/ADR:

reconsiderar package/shared repo cuando se cumpla algo como:

- 3+ consumidores reales;
- API del runtime estable;
- vendor updates frecuentes;
- duplicación del glue comienza a ser significativa;
- versionado independiente aporta valor.

Entonces el vendoring actual debe facilitar esa extracción,
no impedirla.

---

# 23. NO SUBMODULE

Registrar brevemente por qué no se usa ahora:

- añade estado Git adicional;
- clones pueden quedar incompletos;
- CI necesita manejo especial;
- onboarding móvil/contribuidor empeora;
- el beneficio actual es bajo frente al PIN vendorizado.

No declarar que los submodules sean "malos" universalmente.

Sólo no son la opción elegida para este milestone.

---

# 24. GATES M3.3

M3.3 puede marcarse COMPLETE sólo si:

- upstream inspeccionado;
- PIN fijado;
- subset mínimo identificado;
- sync script funciona;
- provenance existe;
- drift check funciona;
- vendor copy no requiere edición manual;
- tests correspondientes pasan.

---

# 25. GATES M3.4

M3.4 puede marcarse COMPLETE sólo si:

- CreatureMind conecta al boundary nativo;
- fake adapter sigue pasando;
- iOS compila;
- Android compila;
- runtime real alcanza llama.cpp;
- al menos un smoke de inferencia demuestra output;
- failure cae a fallback sin corromper save;
- ContextBox no concede authority;
- build/typecheck/tests están limpios.

Si sólo desktop/CI compila:

marcar real-device:

    NOT_DEMONSTRATED

---

# 26. STOP CONDITIONS

DETENER y reportar si:

- bridge upstream requiere copiar gran parte de iSyCode Móvil;
- hay dependencias circulares entre apps;
- TamagotchIA necesita importar app/UI state de iSyCode;
- hay que editar el vendor manualmente para hacerlo funcionar;
- ContextBox necesita contener credentials;
- llama.cpp obtiene game authority;
- integración rompe PWA;
- save schema necesita cambio inesperado;
- iOS y Android requieren runtimes fundamentalmente divergentes;
- la copia fijada empieza a comportarse como un fork independiente.

No refactor grande sin evidencia.

---

# 27. ROLLBACK

Todo M3 debe poder apagarse.

Si el runtime nativo falla:

    feature/local GUS disabled
    current TamagotchIA behavior restored

No hacer migración de saves dependiente de M3.

Eliminar el vendor/runtime debe dejar:

- engine;
- save;
- persona fallback;
- PWA

funcionando.

---

# 28. PROVENANCE DE EJECUCIÓN

Al cerrar el milestone reportar:

    TamagotchIA base SHA
    TamagotchIA resulting SHA
    iSyCodeMovil upstream SHA
    copied source paths
    resulting vendor paths
    hashes
    tests
    build results
    device evidence
    NOT_DEMONSTRATED gaps

Actualizar:

    docs/tamagotchia/ROADMAP.md

con commits exactos.

---

# 29. NO PR TODAVÍA SI ESA ES LA POLÍTICA ACTUAL

Continúa usando la rama existente de TamagotchIA
salvo evidencia de que ya cambió el workflow.

No abrir/mergear PR automáticamente
si el propietario no lo pidió.

Commits pequeños por slice.

Push después de cada checkpoint verificable.

---

# 30. DESPUÉS DE M3

Si M3 queda demostrado:

continuar según roadmap.

No saltar inmediatamente a World/PvP.

La siguiente frontera relevante sigue siendo
la que marque el roadmap actual,
incluyendo Interaction Gate antes de ampliar el contexto remoto.

Especialmente:

> no permitir que NVAPI/Nebius reciba el ContextBox completo
> sólo porque el local ya funciona.

Remote egress sigue fail-closed hasta M5.

---

# PRINCIPIO FINAL

No estamos copiando "el cerebro de iSyCode".

Estamos reutilizando un runtime de inferencia probado.

La mascota sigue viviendo en TamagotchIA.

El bridge puede cambiar.

El GGUF puede cambiar.

El proveedor puede cambiar.

La criatura no.

Y la autoridad del juego jamás pertenece al modelo.
