# 00 — Piso de evidencia actual

## Repos inspeccionados

### TamagotchIA

- Repo: `DannyBaanks/TamagotchIA`
- Rama inspeccionada: `main`
- HEAD observado: `b7fe4b13383d50b1d857ae0574eb110c983157a4`
- Stack observado: TypeScript + Vite + Capacitor.
- `package.json` ya declara Android, iOS, App y Local Notifications de Capacitor.
- Existen `android/`, `ios/` y la PWA/web compartida.
- El motor está en `src/engine/`.
- La persona/LLM está en `src/persona/`.
- El guardado está en `src/store/`.

### Arquitectura que YA existe y debe preservarse

`src/persona/contract.ts` ya implementa una frontera buena:

```text
World + GameEvent
    ↓
personaInput(...)
    ↓
resumen acotado
    ↓
modelo
    ↓
PersonaReply validado
    ↓
voz/animación/memory_candidate
```

El prompt actual ya dice explícitamente que el modelo:

- es la voz de la criatura;
- no es un asistente;
- no inventa eventos;
- no puede cambiar hambre, energía, salud o evolución;
- responde con JSON validado;
- propone `memory_candidate`, pero no muta el juego.

La entrada actual ya contiene:

- nombre, especie y etapa;
- evento actual;
- stats relevantes;
- condiciones derivadas;
- rasgos;
- comida favorita;
- memorias relevantes;
- hora del día;
- texto del jugador cuando aplica.

**Conclusión:** no hay que inventar una segunda arquitectura de persona. Hay que evolucionar este contrato hacia un Context Box persistente y conectar un runtime GUS local.

## iSyCode Móvil como fuente de GUS

Repo inspeccionado: `DannyBaanks/iSyCodeMovil`.

En el árbol actual existen componentes reales que el agente debe revisar antes de copiar/reusar:

### iOS / núcleo local

- `Sources/Model/GUSLlamaBridge.c`
- `Sources/Model/GUSLlamaBridge.h`
- `Sources/Model/LlamaCppInferenceEngine.swift`
- `Sources/Model/GUSLocalModelProvider.swift`
- `Sources/Model/GUSModelManifest.swift`
- `Sources/Model/GUSModelDownloadManager.swift`
- `Sources/Model/GUSDeviceBudget.swift`
- `Sources/Diagnostics/GUSFlightRecorder.swift`
- `Sources/Diagnostics/GUSMetricKitCollector.swift`
- `Catalog/models.json`

### Android

- `android/ISyCodeMovil/app/src/main/cpp/gus_jni.c`
- `android/ISyCodeMovil/app/src/main/java/dev/iyscode/movil/gus/LlamaEngine.kt`
- `.../gus/NativeLlama.kt`
- `.../gus/GusCatalog.kt`
- `.../gus/ModelStore.kt`
- `.../gus/DeviceBudget.kt`
- `.../diagnostics/FlightRecorder.kt`

No asumir que estos paths seguirán idénticos al ejecutar. **Primero inspeccionar.**

## Hechos que NO deben asumirse

- No está demostrado que el runtime GUS de iSyCode Móvil pueda copiarse 1:1 dentro de Capacitor sin bridge nativo adicional.
- No está demostrado qué modelo local es el default ideal para TamagotchIA.
- No está demostrado que iOS y Android deban compartir el mismo wrapper; probablemente compartirán contrato y C/llama.cpp, pero la integración nativa puede diferir.
- No está demostrado que el Context Box deba almacenar conversaciones completas. Este paquete propone explícitamente que NO.
- PvP remoto, matchmaking y servidor autoritativo son fase futura, no parte del primer merge.

## Piso que sí debe conservarse

1. Motor determinista = verdad canónica.
2. GUS nunca escribe stats directamente.
3. Fallback local sin IA debe seguir funcionando.
4. PWA debe seguir siendo jugable aunque no pueda ejecutar GGUF local.
5. iOS/Android deben degradar limpiamente si no hay modelo descargado.
6. La memoria del GUS debe ser auditable, exportable y versionada.
