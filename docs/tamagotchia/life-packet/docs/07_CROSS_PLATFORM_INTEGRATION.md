# 07 — Integración PWA / iOS / Android

## Estado conceptual

TamagotchIA ya comparte una base web/TypeScript y usa Capacitor para iOS/Android. Eso permite mantener el motor/persona/contexto en TS y dejar la inferencia local detrás de plugins/bridges nativos.

## Estrategia recomendada

```text
TypeScript game core
├── engine
├── context box
├── memory policy
├── persona contract
└── CreatureMind interface
        │
        ├── WebRemoteMind
        ├── DeterministicMind
        └── NativeLocalGUSMind
                │
          Capacitor plugin boundary
             ├── iOS native
             └── Android native
```

## iOS

Inspeccionar/reusar del GUS móvil:

- llama.cpp build/linking;
- C bridge;
- model manifest/download/import;
- memory-fit logic;
- sampling;
- flight recorder;
- hash verification.

No copiar UI de iSyCode Móvil. TamagotchIA necesita sólo runtime + catálogo/selección donde aplique.

## Android

Inspeccionar/reusar:

- CMake/llama.cpp;
- JNI bridge;
- Kotlin `LlamaEngine`/model store/catalog;
- memory-fit logic;
- crash breadcrumbs.

## Contrato nativo mínimo

Algo equivalente a:

```ts
interface NativeGUSPlugin {
  listModels(): Promise<ModelInfo[]>;
  loadModel(id: string): Promise<LoadResult>;
  generate(req: NativeGenerateRequest): Promise<NativeGenerateResult>;
  unloadModel(): Promise<void>;
  getDeviceBudget(): Promise<DeviceBudget>;
}
```

El plugin NO debe recibir `World` mutable. Recibe strings/JSON del Context Box.

## Model catalog

No es obligatorio copiar los 22 modelos en V1. Mejor:

1. demostrar 1–3 modelos pequeños;
2. heredar el catálogo completo sólo si el costo de mantenimiento queda compartido/automatizado;
3. evitar dos catálogos divergentes con hashes distintos.

Ideal futuro: una fuente de verdad común generada para ambos repos, pero no introducir un package compartido hasta que la duplicación real lo justifique.

## PWA

Debe conservar:

- juego offline;
- fallback deterministic voice;
- providers remotos opcionales existentes.

Mostrar “GUS local requiere app nativa” si aplica. No hacer que la PWA falle por imports nativos.

## Distribución del modelo

El modelo no debe formar parte del save. Considerar:

- download bajo demanda;
- importar desde Files/Storage;
- hash antes de cargar;
- backup separado;
- eliminación independiente de la criatura.
