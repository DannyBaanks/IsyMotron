# COMPOSE — TamagotchIA × ISyMotron
## Life Runtime, Context Box, Canon/Local, Interaction Gate y frontera OmniHarness

> Copia textual del Compose que entregó el usuario el 2026-09-30. Extiende el
> paquete `life-packet/` (en esta misma carpeta). El seguimiento de trabajo está
> en [`ROADMAP.md`](ROADMAP.md).

### Naturaleza de este Compose

Este documento EXTENDE el paquete `tamagotchia-gus-life-packet.zip` que ya recibiste.

NO lo reemplaces ni reinterpretas desde cero.

El ZIP sigue siendo el piso arquitectónico de GUS + Context Box + memoria persistente.
Este Compose incorpora decisiones tomadas DESPUÉS de generar ese paquete y cambia
considerablemente el horizonte del sistema.

La relación conceptual ahora es:

    ISyMotron:
    "el modelo propone; la autoridad decide; queda un recibo"

    TamagotchIA:
    "GUS propone; el motor del juego decide; queda historia verificable"

Es la MISMA frontera de autoridad aplicada a dos dominios distintos.

Antes de editar:
1. inspecciona el estado ACTUAL del repositorio;
2. contrasta ese estado con el ZIP;
3. identifica qué documentos/arquitectura del ZIP ya quedaron superados;
4. no inventes paths, APIs, tipos ni comportamiento;
5. no hagas refactors ajenos;
6. preserva compatibilidad con PWA/iOS/Android cuando sea razonable;
7. clasifica afirmaciones como DEMONSTRATED / INFERRED / NOT_DEMONSTRATED;
8. usa evidencia del repo y de pruebas, no narrativa.

No conviertas esta visión completa en un PR gigantesco.

Primero hay que obtener arquitectura y contratos limpios.
Después se implementan slices pequeños.

---

# 0. PISO DE EVIDENCIA

## Ya existente / a verificar directamente en repo

TamagotchIA actualmente tiene una separación útil entre:

- motor del juego;
- estado persistente;
- memoria;
- proveedor/persona;
- UI;
- PWA/native wrappers.

La IA/persona recibe un estado acotado y su respuesta no debe convertirse
directamente en una mutación del juego.

Preservar esa frontera.

El estado de la criatura NO debe migrarse hacia el LLM.

El modelo nunca será la fuente de verdad de:

- hambre;
- energía;
- salud;
- inventario;
- XP;
- crecimiento;
- evolución;
- victorias;
- derrotas;
- cooldowns;
- progreso Canon;
- relaciones verificables;
- estado del mundo.

El modelo puede expresar, interpretar, proponer o reaccionar.

El motor/Authority decide.

---

# 1. TESIS CENTRAL — LA MASCOTA NO ES EL MODELO

Ésta pasa a ser una invariante de producto.

> La mascota no es el modelo.
> El modelo es solamente el cerebro que la interpreta en ese momento.

La identidad debe sobrevivir a:

- cambio de GGUF;
- cambio de proveedor;
- modelo local → modelo remoto;
- modelo remoto → modelo local;
- reinstalación/restauración válida;
- cambio futuro de runtime de inferencia.

Ejemplo permitido:

    hoy      SmolLM
    mañana   Qwen
    después  Nemotron remoto

y sigue siendo exactamente la misma criatura.

La identidad debe residir aproximadamente en conceptos como:

    PetIdentity
    CanonState / LocalState
    LifeLog
    RelationshipState
    Memory
    ContextBox

NO en pesos/modelos/prompts particulares.

Principio de UX:

> cambias el cerebro, no matas a la mascota.

---

# 2. OBJETIVO EMOCIONAL

El usuario debe generar vínculo con LO QUE CRIÓ,
no con Qwen, Nemotron, Claude, NVIDIA ni ningún proveedor.

Queremos que después de meses diga:

> "éste es MI Malbolgato"

porque reconoce:

- cómo lo cuidó;
- qué experiencias tuvo;
- qué hábitos desarrolló;
- sus preferencias;
- sus rivales;
- sus victorias y derrotas;
- cómo reacciona;
- cosas que vivieron juntos.

No:

> "me gusta este modelo".

Por tanto, la personalidad final debe poder ser consecuencia de:

    predisposición de especie
    + rasgos iniciales
    + crianza
    + eventos reales
    + hábitos
    + relación con el usuario
    + recuerdos
    + historial social
    + interpretación actual de GUS

No convertir esto en una tabla de personalidad rígida todavía.
Primero diseñar el contrato.

---

# 3. CONTEXT BOX

El Context Box pasa a ser infraestructura central.

No es "guardar todo el chat y volverlo a mandar".

Debe ser una proyección acotada y compilada de la vida de la criatura.

Conceptualmente:

    LIFE STATE
        |
        +-- identidad estable
        +-- estado actual
        +-- hábitos
        +-- relación
        +-- recuerdos relevantes
        +-- eventos recientes
        +-- contexto de conversación necesario
        +-- contexto del mundo permitido
        |
        v
    CONTEXT COMPILER
        |
        v
    CONTEXT BOX
        |
        v
    GUS actual

El modelo sólo ve la ventana necesaria.

## Restricción importante aprendida de iSyCode Móvil

NO diseñar el Context Box suponiendo que siempre hay 4K/8K/32K tokens.

Hay modelos locales de contexto pequeño.

El presupuesto debe ser explícito y medido.

No establecer arbitrariamente:

    "pet summary = 1500-2000 tokens"

si el runtime usa 2048 y además necesitamos:

- system;
- identidad;
- personalidad;
- evento;
- mensaje;
- output budget.

Crear un `ContextBudget` o equivalente conceptual.

Ejemplo:

    total_context
      - reserved_output
      - system_contract
      - current_turn
      = available_pet_context

El compiler comprime hasta ese límite.

Debe degradarse con gracia.

Prioridad propuesta:

1. contrato/safety;
2. identidad;
3. estado relevante actual;
4. evento actual;
5. recuerdos directamente relevantes;
6. relaciones;
7. historia resumida;
8. detalles narrativos prescindibles.

No fijar números finales sin benchmark.

---

# 4. PREFIX / CACHE / LATENCIA

Investigar si el runtime local actual permite reutilizar KV/prefix de manera segura.

Idealmente ordenar contexto:

    estable --------------------------> volátil

    system
    identidad
    especie
    personalidad estable
    historia compactada
    recuerdos relevantes
    estado actual
    evento actual
    mensaje actual

Si el runtime permite reutilizar el prefijo estable,
evitar reprocesarlo en cada respuesta.

NO afirmar que esto reduce X segundos sin benchmark real.

Medir:

- TTFT;
- prefill tok/s;
- generation tok/s;
- RAM;
- thermal;
- modelo;
- hardware;
- tamaño del Context Box.

Si no existe soporte limpio para prefix reuse hoy,
documentarlo y continuar sin hacks.

---

# 5. OUTPUT DE GUS

El ZIP propuso JSON estructurado.

Mantener la idea del contrato,
pero incorporar la realidad de modelos pequeños.

Investigar primero:

A) grammar/constrained decoding de llama.cpp;
B) validación post-output;
C) fallback determinista.

Orden deseado:

    constrained generation
        |
        v
    schema validation
        |
        v
    deterministic fallback

Si las grammars funcionan en nuestras superficies iOS/Android,
preferirlas para estructura.

Pero NO hacer que la existencia de JSON perfecto sea requisito
para que la mascota pueda hablar.

Fallback aceptable:

    GUS genera speech
    código decide emotion/intent/animation

La criatura debe seguir funcionando si GUS falla.

---

# 6. MEMORIA: EVENTOS PRIMERO, LLM DESPUÉS

Don Zelaya dejó una lección importante:

un modelo pequeño puede:

- inventar;
- repetir;
- interpretar mal;
- fallar al corregirse.

Por eso en v1:

NO permitir que el LLM sea fuente primaria de la autobiografía.

Los recuerdos verificables deben derivarse de eventos reales.

Ejemplo:

    GameEvent
       |
       +-> MemoryCandidate determinista
       |
       +-> LifeLog
       |
       +-> Context Compiler

GUS puede PROPONER:

    "este momento parece importante"

pero el sistema decide si corresponde a un evento real.

No dejar todavía que un modelo resuma arbitrariamente 6 meses
de historia y sobrescriba el pasado.

La memoria puede compactarse,
pero debe conservar provenance al evento fuente cuando sea importante.

---

# 7. TAMAGOTCHIA LOCAL vs TAMAGOTCHIA CANON

Ésta es una decisión NUEVA y no estaba suficientemente desarrollada en el ZIP.

Necesitamos DOS dominios claros.

## TamagotchIA Local

Es laboratorio.

El usuario puede modificar lo que quiera.

Dev mode puede eventualmente permitir experimentar con:

- stats;
- hunger;
- energy;
- bond;
- mood;
- XP;
- stage;
- traits;
- inventory;
- cooldowns;
- personalidad;
- memoria;
- reloj;
- semillas;
- eventos;
- evolución;
- combinaciones absurdas.

Objetivo:

> probar builds puercas rápidamente.

Ejemplo:

    quiero saber si
    alta velocidad + baja confianza + agresividad + skill X
    produce algo interesante

Local permite comprobar la idea sin criar durante una semana.

NO intentar balancear Local.

Local puede estar completamente roto.

## TamagotchIA Canon

Es el dominio elegible para progreso competitivo verificable.

Aquí la build NO se edita.

Se CRÍA.

El usuario puede descubrir una build en Local,
pero para poseerla en Canon tiene que conseguirla mediante:

- cuidado;
- entrenamiento;
- alimentación;
- descanso;
- juego;
- relación;
- experiencias;
- decisiones;
- tiempo;
- reglas válidas.

Esto es crítico:

> Local permite teoría.
> Canon obliga a vivir la progresión.

Eso crea vínculo con la criatura y hace que la crianza SEA parte del buildcraft.

No diseñar Canon como pay-to-win.

---

# 8. CANON NACE CANON

Primera política preferida:

> una criatura Canon nace Canon.

No intentar "sanitizar" después una partida Local arbitraria.

Estado conceptual:

    mode = canon
    ruleset_version = canon-v1
    dev_edits = disabled
    integrity_chain = enabled
    eligible_for_pvp = true

Si alguien quiere experimentar con su criatura Canon:

NO convertir el original.

Crear:

    "Crear copia de laboratorio"

Resultado:

    Canon original
       |
       +---- fork ----> Local clone

La copia Local puede guardar:

    forked_from_canon_hash

para provenance.

Pero jamás vuelve a Canon.

Esto evita:

    Canon -> dev edits -> "limpiar" -> Canon

que sería difícil de asegurar y explicar.

---

# 9. INTEGRIDAD CANON

Diseñar desde temprano:

- `ruleset_version`;
- event log append-only o equivalente;
- deterministic reconstruction donde aplique;
- state hash;
- history hash;
- receipts;
- taint/provenance;
- migration explícita entre rulesets.

NO vender hashes locales como anti-cheat perfecto.

En un teléfono completamente controlado por un atacante,
un cliente modificado puede falsificar estado local.

Por tanto distinguir:

## Offline / nearby Canon

Puede ser:

> válido según el protocolo y receipts del cliente.

NO:

> criptográficamente imposible de hackear.

## Hosted competitive Canon futuro

Un servidor autoritativo puede elevar mucho la confianza.

Usar CryptoKit / Android Keystore si encaja con la implementación real,
pero NO inventar criptografía propia.

---

# 10. BUILDCRAFT DERIVADO DE CRIANZA

Diseñar stats/traits para permitir que dos criaturas de la misma especie
acaben siendo distintas por cómo fueron criadas.

Ejemplos conceptuales, NO números finales:

    comida/cuidado    -> energía / constitución
    sueño             -> recovery
    entrenamiento     -> fuerza / técnica
    juego             -> agilidad / curiosidad
    vínculo           -> confianza
    descuido          -> estrés / comportamiento
    experiencias      -> rasgos persistentes

Las relaciones no tienen que ser lineales.

Una build fuerte puede tener tradeoffs.

Pero Canon debe limitar progreso por reglas,
no por dinero/computación contratada.

---

# 11. INTERACTION GATE

Nueva pieza central.

Separar dos permisos que NO deben confundirse:

    CONTEXT GATE
    "¿qué puede leer esta inteligencia?"

    CONTRIBUTION GATE
    "¿qué puede salir para investigación/entrenamiento?"

Son permisos independientes.

---

# 12. CONTEXT GATE

Definir clases conceptuales de información.

Por ejemplo:

    PET_CANON_STATE
    PET_LIFE_LOG
    PET_MEMORY
    PET_RELATIONSHIPS
    USER_CONVERSATION
    USER_PRIVATE_CONTEXT
    DEVICE_METADATA
    SECRETS

Un GUS LOCAL puede recibir más contexto si el usuario lo autoriza.

Un GUS REMOTO recibe sólo lo necesario.

Secrets:

    API keys
    credentials
    tokens
    arbitrary files
    privileged device state

NO deben entrar al Context Box del modelo.

Debe existir:

    REMOTE BLOCK TOTAL

Si el usuario lo activa:

    egress to remote intelligence = 0

No "menos".

CERO.

La mascota sigue existiendo y usa fallback/local si existe.

---

# 13. CONTRIBUTION GATE

Separado completamente del Context Gate.

Opt-in.

OFF por defecto.

Posibles categorías:

    [ ] game events
    [ ] progression statistics
    [ ] battle traces
    [ ] anonymized care patterns
    [ ] pet dialogue
    [ ] player-written text
    [ ] derived memories
    [ ] model outputs

Siempre excluido salvo diseño explícito extraordinario:

    credentials
    API keys
    raw device identifiers
    precise location
    unrelated files

No asumir que "usar NVAPI" implica permiso de entrenamiento.

Inference permission y training/research permission son contratos distintos.

Conceptualmente:

    InferenceContextPermission
    TrainingContributionPermission
    ResearchExportPermission

No implementar recolección real hasta revisar además
los términos/licencias de cada proveedor/modelo.

---

# 14. PRESETS DE PRIVACIDAD

Evitar UI con 40 toggles obligatorios.

Proponer presets claros:

    PRIVADO
    todo local / mínimo egress requerido

    MASCOTA SOLAMENTE
    información sobre la criatura;
    no contexto personal del humano

    INVESTIGACIÓN
    subset sanitizado y explícito

    PERSONALIZADO
    control por categoría

Más:

    BLOQUEO REMOTO TOTAL

---

# 15. GUS LOCAL + GUS REMOTO

Objetivo:

la misma criatura puede ser interpretada por:

- llama.cpp local;
- modelos descargados;
- NVIDIA/NVAPI;
- Nebius;
- otros providers futuros.

El proveedor NO es la identidad de la criatura.

Necesitamos un adapter/routing seam.

Ejemplo:

    ContextBox
       |
       v
    GUSProvider
       |
       +-> LocalLlamaCpp
       +-> NVIDIA/NVAPI
       +-> Nebius
       +-> Other

No hardcodear TamagotchIA alrededor de un modelo específico.

Los modelos remotos NO "entran físicamente al sandbox local".

Se les construye una proyección permitida del sandbox:

    Local Pet Sandbox
          |
          v
    Interaction Gate
          |
          v
    Remote Context Projection
          |
          v
    External Model

Mantener esa terminología correcta.

---

# 16. ISyMOTRON COMO CAPA GENERAL

TamagotchIA no es el sistema completo.

Es UNA vertical del mismo runtime.

La arquitectura mayor debe preservar:

    intelligence
    compute
    capabilities
    authority
    transport
    receipts

Conceptualmente:

    INTELLIGENCE
    - local model
    - remote model
    - human
    - deterministic engine

    COMPUTE
    - phone
    - local PC
    - remote PC
    - datacenter
    - community node
    - cloud sandbox

    CAPABILITY
    - filesystem
    - shell
    - browser
    - game
    - notifications
    - screen/input
    - model inference

    AUTHORITY
    - scopes
    - approvals
    - ownership
    - effect boundary

    TRANSPORT
    - local IPC
    - HTTPS
    - MCP
    - WebSocket
    - Tailscale
    - SSH/etc. where appropriate

No implementar una abstracción gigante todavía.
Sólo conservar el contrato para no cerrarnos puertas.

---

# 17. BROKER

Broker NO es Authority.

Broker decide:

- quién;
- dónde;
- con qué capacidades disponibles;
- sobre qué compute;
- mediante qué ruta.

Pero solicitar una acción no autoriza la acción.

Cadena conceptual:

    model / user / GUS
          |
          v
        Broker
          |
          v
      Authority
          |
          v
      Sentinel
          |
          v
      Capability
          |
          v
       Receipt

Preservar fail-closed.

Comprometer Broker NO debe significar poseer todas las máquinas.

---

# 18. REVIVER

Queremos evitar el problema de clientes remotos que,
por no tener acceso a la máquina,
tienen que recibir una biblia de contexto cada turno.

NO:

    remote Claude
      <- filesystem entero
      <- terminal transcript enorme
      <- git state serializado
      <- herramientas serializadas
      <- contexto creciente

Preferimos:

    remote intelligence
         |
         | "haz X en Victus"
         v
       Broker
         |
         v
       Reviver
         |
         v
    agent residente
    en esa máquina
         |
         v
      ISyCode
         |
         v
     ISyMotron
         |
         v
    authorized effects

El modelo remoto COORDINA.

El agente cercano al entorno EJECUTA.

El contexto operacional permanece cerca del entorno que lo produce.

Reviver debe poder conceptualmente:

- localizar worker existente;
- despertar/reanudar sesión;
- crear uno si hace falta;
- restaurar contexto mínimo;
- entregarle la tarea;
- devolver status/receipt.

Investigar primero el Reviver real existente en Munder.
NO inventar otra implementación si ya existe una reutilizable.

---

# 19. ISyCODE COMO TUI NATIVA DEL NODO

Dirección deseada:

ISyCode no sólo como interfaz humana,
sino como superficie textual estándar del nodo ISyMotron.

Conceptualmente:

    ISyCode runtime
       |
       +-> human TUI
       |
       +-> agent surface

Ambos deben terminar en las MISMAS fronteras de Authority/Sentinel.

Evitar:

    human path -> seguro
    agent path -> shell privilegiado secreto

NO asumir que ya existe literalmente:

    isycode --agent

Inspectar antes.

Si no existe,
tratarlo como dirección de diseño, no hecho actual.

---

# 20. MCP + OAUTH / PROVIDER IDENTITY

Queremos que inteligencias externas puedan conectarse
a una cuenta/instalación ISyMotron sin darles autoridad ilimitada.

Separar:

    AUTHENTICATION
    "¿quién eres?"

de:

    AUTHORIZATION
    "¿qué puedes hacer aquí?"

Adaptadores futuros pueden usar:

- OAuth;
- API key;
- device code;
- pairing token;
- local socket;
- service account;
- otro mecanismo.

Broker/Authority no debe depender del método específico.

Concepto:

    ProviderIdentity
    SessionIdentity
    RequestedCapabilities
    GrantedCapabilities

Claude/OpenAI/NVIDIA/etc. pueden tener adapters distintos.

---

# 21. MCP NO ES TRANSPORTE UNIVERSAL

MCP encaja bien para:

- tools;
- resources;
- commands;
- context;
- actions.

No forzar por MCP:

- screen streaming;
- mouse;
- audio realtime;
- continuous game events;
- avatar input realtime.

Separar:

    MCP
    = capability protocol

    Realtime channel
    = WebSocket / QUIC / Tailscale / local IPC / etc.

Ambos terminan en la MISMA Authority.

---

# 22. ADAPTIVE POLLING DEL BROKER

Para tareas remotas/largas queremos notificación casi en vivo
sin desperdiciar CPU/red consultando cada segundo.

Diseñar un poll scheduler adaptativo.

Ejemplo inicial, NO requisito rígido:

    tarea corta:
    ~1-2 min

    tarea larga:
    ~3-4 min

    batch/background:
    más largo

El AGENTE puede recomendar cambiar temporalmente la cadencia.

Ejemplo:

    "ahora corro tests cortos"
    -> poll más frecuente

    "ahora espero build de 20 min"
    -> poll menos frecuente

Además aplicar backoff cuando no hay progreso.

Distinguir:

    HEARTBEAT
    sigo vivo

    PROGRESS
    cambió trabajo

    EVENT
    terminé / fallé / necesito aprobación / artifact listo

Si existe canal activo,
los eventos importantes deben ser PUSH.

Polling es fallback/resiliencia.

Objetivo:

    push when possible
    adaptive polling otherwise

NO crear un polling loop agresivo fijo.

---

# 23. TAMAGOTCHIA WORLD — HORIZONTE, NO MVP

Diseñar contratos ahora.
NO construir el MMO durante este milestone.

La idea futura:

el usuario puede mandar su TamagotchIA a un mundo hospedado.

NO sería un backup pasivo.

Sería:

    local creature
         |
      handoff
         |
         v
    World Authority
         |
    continúa viviendo
         |
      return
         |
         v
    misma identidad,
    nuevo estado/historia

Cuando regresa,
NO es igual que cuando salió porque VIVIÓ.

---

# 24. HANDOFF / LEASE DE AUTORIDAD

Para Canon no deben existir dos versiones autoritativas simultáneas.

Conceptualmente:

    LOCAL AUTHORITY
          |
        handoff
          |
          v
    WORLD AUTHORITY
          |
        return
          |
          v
    LOCAL AUTHORITY

Generar receipts conceptuales:

    pet_id
    departure_state_hash
    ruleset_version
    entered_at
    world_id

y al volver:

    return_state_hash
    events_since_departure
    relationships_changed
    battles
    memories
    elapsed

No asumir criptografía perfecta.
Definir provenance/replay.

Mientras la mascota Canon está en World,
un juego local alterno podría ser una rama/simulación NO Canon,
pero no resolver ahora.

---

# 25. WORLD PET SANDBOX

Cada criatura hospedada debe vivir dentro de una superficie acotada.

GUS puede:

- percibir información permitida;
- hablar;
- elegir entre acciones disponibles;
- proponer intención.

NO puede:

- escribir estado global;
- editar stats arbitrariamente;
- acceder a otros sandboxes;
- tocar host;
- usar secrets;
- concederse capabilities.

Cadena:

    GUS
      |
    intent
      |
    World Engine / Authority
      |
    canonical event
      |
    LifeLog

---

# 26. AVATAR / TAKEOVER

Future World debe permitir dos modos:

    AUTONOMOUS
    GUS decide intenciones permitidas

    AVATAR / POSSESSED
    humano toma control directo

Cuando el humano sale,
GUS vuelve a actuar.

No mezclar esto todavía con implementación de combate.

Sólo dejar el seam.

---

# 27. SOCIAL WORLD FUTURO

Relaciones entre criaturas pertenecen a TamagotchIA World:

- amistad;
- rivalidad;
- equipos;
- visitas;
- relaciones;
- eventualmente pareja/matrimonio;
- familia/lineage si se decide.

NO meter "wedding system" en el hackathon :P

Primero:

    criatura
    identidad
    memoria
    mundo
    relaciones verificables

Después se agregan sistemas sociales.

---

# 28. PVP FUTURO

Preservar contrato reproducible.

Ideal conceptual:

    initial_state_A
    initial_state_B
    ruleset_version
    deterministic_seed
    actions[]
    final_state
    result

El LLM NO decide:

    damage
    winner
    RNG
    legal moves
    cooldowns

GUS puede aportar:

    tactical intent
    personality
    style
    risk preference

El combat engine decide lo válido.

---

# 29. COMPUTE TIERS / MONETIZACIÓN FUTURA

La monetización del World debe corresponder
a consumo real de infraestructura.

No vender arbitrariamente "memoria premium".

Conceptualmente:

    LOCAL
    compute del usuario
    -> gratis

    WORLD LITE
    poca frecuencia de actividad
    -> barato/gratis

    WORLD ACTIVE
    más simulación/social/GUS
    -> mayor compute

    WORLD CHAOS
    alta densidad de actividad
    -> mayor CPU/GPU/storage

Pero esto NO puede convertirse en:

    paga más -> sube stats más rápido

Evitar pay-to-win.

---

# 30. COMPUTE DENSITY != COMPETITIVE POWER

Separar:

    narrative/activity budget

de:

    Canon progression budget

Una criatura con muchísimo compute puede:

- vivir más escenas;
- hablar más;
- conocer más criaturas;
- producir más historia;
- tener mundo más activo.

Pero no necesariamente:

- entrenar 40x más;
- ganar 40x XP;
- superar límites Canon;
- tener RNG favorable.

Canon debe imponer límites de progreso independientemente
de cuántos ticks pagó alguien.

---

# 31. COLLAB COMPUTE / P2P

Futuro modo:

> presta tu PC como semi-server comunitario.

Usuario define límites:

    CPU %
    RAM
    GPU yes/no
    red
    horario
    storage
    pause inmediato

A cambio puede recibir compute/credits/beneficios.

Arquitectura:

    Community Pool
    Sponsor Pools
    Own Datacenter
    Local Nodes

Broker puede seleccionar substrate por:

    privacy
    authority
    cost
    latency
    hardware
    trust
    availability

NO asumir que todos los workloads son transferibles.

---

# 32. COMMUNITY NODES SON HOSTILES POR DEFAULT

Nunca enviar a nodos aleatorios:

- API keys;
- credentials;
- private user history completo;
- secrets;
- authority root;
- editable Canon save sin protección.

Preferir jobs encapsulados.

Ejemplo:

    simulate_epoch(
      state,
      ruleset,
      seed,
      ticks
    )

Resultado:

    trace
    result
    receipt/hash

Para trabajo determinista,
podemos:

- reproducir;
- sample-check;
- replicar en más de un nodo;
- comparar resultados.

Para LLM inference comunitaria,
mandar sólo Context Box sanitizado
y tratar el output como PROPUESTA.

Nunca como efecto.

---

# 33. COLLAB NODE NO DEBE SER MALWARE CON BUEN MARKETING

La persona que presta su máquina debe ver:

- qué comparte;
- cuánto CPU;
- cuánto RAM;
- cuánto GPU;
- red;
- jobs;
- historial;
- consumo;
- pause/stop;
- receipts.

Authority/Sentinel protegen AMBOS lados:

1. infraestructura del usuario frente al agente;
2. computadora colaboradora frente al sistema comunitario.

---

# 34. SPONSOR COMPUTE

La misma abstracción de compute pools permite sponsors.

Un sponsor puede aportar:

- GPU hours;
- CPU;
- storage;
- network;
- hosted inference;
- regions;
- grants.

No hardcodear exclusividad.

Broker debería poder ver un sponsor simplemente como otro pool
con atributos:

    hardware
    region
    quota
    allowed_workloads
    privacy_class
    availability
    trust

Esto permite que un sponsor subsidie "vida"
sin darle autoridad sobre el ecosistema.

NO implementar billing/sponsor marketplace ahora.

Sólo no cerrar esta posibilidad.

---

# 35. HACKATHON NVIDIA × NEBIUS

Para el hackathon congelar alcance.

NO intentar construir:

- World completo;
- matrimonio;
- P2P masivo;
- economía;
- server authoritative ranked;
- federación completa.

La demo debería probar una columna vertebral clara.

Ideal:

    Intelligence
       |
    Broker/routing
       |
    Context/Sandbox
       |
    Authority
       |
    Capability
       |
    Receipt

Aplicada a DOS superficies.

## Superficie A — TamagotchIA

Demostrar:

- misma criatura;
- cerebro local;
- cerebro remoto NVIDIA/Nebius;
- Context Box;
- Interaction Gate;
- cambiar modelo sin perder identidad;
- remote block;
- engine sigue siendo autoridad.

## Superficie B — Computer

Demostrar una capacidad real de ISyMotron:

    remote intelligence
         |
       Broker
         |
       Reviver
         |
    local agent
         |
      ISyCode
         |
    Authority/Sentinel
         |
    authorized effect
         |
      receipt

No hace falta que sea enorme.

UNA capacidad real, bien demostrada,
vale más que 20 mocks.

---

# 36. BOOTSTRAP / OMNIHARNESS

Horizonte UX:

    isymotron up

y que el nodo descubra/configure lo disponible.

No implementar todo ahora.

Dirección:

    ✓ workspace
    ✓ broker
    ✓ authority
    ✓ sentinel
    ✓ runtime

    found:
      local models
      NVIDIA credentials
      Nebius
      Tailscale
      GitHub
      machines
      mobile device
      etc.

Después el usuario piensa en:

    añadir inteligencia
    añadir computadora
    añadir capacidad

no:

    configurar manualmente 27 servicios.

El login/cloud identity NO concede automáticamente autoridad local.

Identity != Authority.

---

# 37. MODELO DE RECIBOS

Unificar mentalmente:

## Computer receipt

    requested action
    capability
    authority decision
    effect
    result

## TamagotchIA receipt/event

    prior state
    legal action/event
    engine decision
    resulting state

No forzar mismo formato físico todavía,
pero estudiar si existe un contrato compartido mínimo:

    actor
    request
    authority
    effect
    evidence/provenance
    timestamp/version

Esto puede convertirse después
en una pieza central de ISyMotron.

---

# 38. PLAN DE IMPLEMENTACIÓN

## M0 — INSPECTION ONLY

No tocar código.

Entregar:

- commit/ref actual;
- árbol relevante;
- estado de engine/persona/memory/store/providers/native;
- qué partes del ZIP ya existen;
- qué partes faltan;
- qué docs están stale;
- qué se puede reutilizar de iSyCode Móvil / ISyMotron;
- riesgos;
- tests actuales;
- evidencia real vs claims.

Especialmente revisar:

- context window actual;
- llama.cpp bridge reutilizable;
- sampling;
- no-think;
- JSON/grammar support;
- UTF-8 path;
- model store/catalog;
- SHA verification;
- crash recorder;
- provider abstraction;
- mobile native bridge.

Si M0 contradice este Compose:
DETENER la suposición y reportar evidencia.

## M1 — DATA CONTRACT

Diseñar primero:

- PetIdentity;
- LifeLog;
- ContextBox;
- ContextBudget;
- provenance;
- versioning;
- Local/Canon marker;
- ruleset version.

Tests antes de integración pesada.

## M2 — CONTEXT COMPILER

Implementar bounded context.

Tests:

- never exceeds budget;
- stable priorities;
- irrelevant history drops first;
- current state retained;
- secrets never included;
- deterministic output given same state/config.

## M3 — LOCAL GUS

Integrar runtime local reutilizando infraestructura existente
si realmente aplica.

Preservar fallback.

No bloquear PWA si native runtime no existe ahí.

## M4 — STRUCTURED OUTPUT

Probar grammar/constrained output.

Si no es fiable/portable,
speech-only + deterministic metadata.

No atascar proyecto por JSON.

## M5 — INTERACTION GATE

Primero data model + policy.

Local/remote permission distinction.

Remote Block Total.

No training export todavía salvo mock de UX/schema.

## M6 — REMOTE GUS

NVIDIA/NVAPI/Nebius detrás del mismo provider interface.

Demostrar:

    local brain -> remote brain -> local brain

sin perder identidad.

## M7 — LOCAL/CANON FOUNDATION

Agregar dominio e invariantes,
NO PvP completo.

Canon born Canon.

Clone/fork to Local.

No Local -> Canon.

## M8 — RECEIPTS / LIFE LOG

Eventos reproducibles y provenance.

No inventar anti-cheat perfecto.

## M9 — ISyMOTRON VERTICAL

Una integración real:

    Broker -> Reviver -> local worker -> ISyCode/Authority -> effect -> receipt

Sólo después de inspeccionar repos correspondientes.

## M10 — HACKATHON DEMO

Polish + benchmark + video + evidence.

---

# 39. TEST MATRIX MÍNIMA

Necesitamos demostrar por separado:

IDENTITY:
- cambio de modelo conserva mascota;
- cambio local/remoto conserva mascota.

AUTHORITY:
- GUS no puede editar stats;
- prompt injection del usuario no concede authority;
- output inválido no muta estado.

CONTEXT:
- budget enforced;
- priority stable;
- secrets excluded;
- remote gate respected.

FAILURE:
- modelo ausente;
- modelo crash;
- malformed JSON;
- timeout;
- network unavailable;
- remote blocked;
- context overflow.

CANON:
- dev mode no modifica Canon;
- fork genera Local;
- Local no recupera eligibility;
- ruleset version persisted.

PRIVACY:
- remote provider recibe sólo categorías permitidas;
- Remote Block Total produce zero remote inference traffic.

RECEIPTS:
- state transition has provenance;
- replay where deterministic matches expected output.

Do not claim tests passed until executed.

---

# 40. STOP CONDITIONS

Detener y reportar antes de seguir si:

- hay que romper save compatibility sin migration;
- hay que duplicar una infraestructura ya existente en iSyCode Móvil;
- TamagotchIA necesita acceso privilegiado fuera de sandbox;
- el modelo puede mutar engine state directamente;
- secrets pueden entrar al Context Box;
- Canon depende de confiar ciegamente en un LLM;
- implementation requires giant unrelated refactor;
- PWA stops working merely because local-GGUF support is native-only;
- provider-specific code infects core pet identity/state;
- repo actual contradice una premisa importante de este Compose.

---

# 41. ROLLBACK

Cada milestone debe poder revertirse aisladamente.

No migrar saves destructivamente.

Antes de modificar schema persistente:

- fixture del formato anterior;
- migration test;
- roundtrip;
- corrupt input handling;
- backup/restore check.

Local GUS debe poder deshabilitarse
y regresar a current fallback/provider behavior.

Interaction Gate debe fail closed.

---

# 42. PROVENANCE

Registrar para cada cambio importante:

- repo;
- base SHA;
- branch;
- files changed;
- tests executed;
- environment;
- model/runtime version where relevant;
- evidence generated;
- known gaps.

No usar:

    "works on iPhone"

si sólo corrió desktop CI.

No usar:

    "anti-cheat"

si sólo existe hash local.

No usar:

    "private"

si remote provider recibió contexto.

Crear rápido.
Declarar lento.

---

# 43. ENTREGABLE INMEDIATO

Primero quiero M0.

No quiero todavía que conviertas toda esta visión
en 8,000 líneas de implementación.

Después de inspeccionar, entrega:

1. evidencia actual;
2. mapa del repo;
3. qué reutilizarías;
4. qué NO reutilizarías y por qué;
5. delta entre ZIP y repo;
6. delta entre ZIP y ESTE Compose;
7. propuesta exacta de M1-M3;
8. archivos que tocarías;
9. tests que agregarías;
10. riesgos/bloqueos.

Si M0 está limpio,
puedes continuar automáticamente con el slice mínimo de M1
sin pedir confirmación por cada archivo,
siempre que:

- sea pequeño;
- esté cubierto por tests;
- no cambie autoridad;
- no rompa saves;
- no haga refactors ajenos.

Todo lo posterior a M1 debe seguir por milestones verificables.

---

# 44. IDEA QUE NO DEBEMOS PERDER

El objetivo NO es hacer:

> "un Tamagotchi con chatbot"

El objetivo es demostrar una arquitectura donde:

> una identidad persistente puede ser interpretada por inteligencias intercambiables,
> habitar distintos substrates de cómputo,
> conservar memoria e historia,
> y producir efectos sólo a través de una autoridad externa verificable.

TamagotchIA hace esa idea visible y emocional.

ISyMotron la generaliza a computadoras, agentes y capacidades.

TamagotchIA World,
si algún día se construye,
la extiende a continuidad de existencia hospedada.

El modelo propone.

La autoridad decide.

El mundo recuerda.
