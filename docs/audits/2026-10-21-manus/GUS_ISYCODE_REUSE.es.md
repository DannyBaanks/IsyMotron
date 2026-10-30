# GUS: antecedente físico de iSyCodeMovil y reutilización

Fecha: 2026-10-21. Inspección de código e historial; no se modificó iSyCodeMovil.

## El caso «Don Zelaya»

El usuario confirmó en esta conversación que GUS ya respondió en modo avión en iSyCodeMovil con Qwen 0.5B, Smol y otro Qwen pequeño. Señaló como antecedente un caso en los commits.

El caso se encontró en el [commit bea62f4](https://github.com/DannyBaanks/iSyCodeMovil/commit/bea62f47e4532adfe7ee8dce20de35985e5e4e41), del 30 de septiembre. Su mensaje registra una prueba física con **Qwen1.5 1.8B**, que respondió a la pregunta sobre el presidente de México en 2000 inventando «José Luis Zelaya» y repitiendo hasta agotar tokens. La [fusión 799cbb8](https://github.com/DannyBaanks/iSyCodeMovil/commit/799cbb8abf4720f24a3aa5604bc93122a63d33f6) lo denomina expresamente **the "Don Zelaya" fix**.

La corrección introdujo muestreo de chat con temperatura 0.6, top-k 40, top-p 0.9, min-p 0.05 y penalización 1.15 sobre 128 tokens; eliminó además una aceptación doble del token. El smoke test del bridge conserva la pregunta como regresión de repetición. Corregir el bucle no demuestra que el modelo deje de inventar hechos.

## Comprobaciones entre proyectos

| Elemento | Resultado |
|---|---|
| Pin de origen en IsyMotron | iSyCodeMovil `9c8a659840045cb31da7b501022645a194f4422d` |
| Ancestro del pin | `bea62f4` está incluido; comprobado con `git merge-base --is-ancestor` |
| Bridge C | Idéntico byte por byte entre iSyCodeMovil actual, el pin e IsyMotron; SHA-256 `b79fb3e4a50a5d8d7393e56aeefe1187dc20ca8ebaaf100d116dc0ed32029efb` |
| Header C | Idéntico; SHA-256 `c521205b8d5e4a7f796cc9db22e9ffdaac6f7505a73efd2e623d264f64af2353` |
| llama.cpp | Ambos fijan `842b1880415d6f508f03b789e5ce70194def7bfd` |
| Qwen2.5 0.5B y SmolLM2 360M | Mismos SHA-256 de modelos en los dos catálogos |
| Sampling de IsyMotron iOS | El plugin ya llama `gus_llama_default_chat_sampling()` y la función sampled; hereda el arreglo |
| Integridad del snapshot | `node mobile/tools/sync-gus-runtime.mjs --verify`: pasa |

La variante de Smol usada físicamente no quedó identificada en el reporte del usuario; no se atribuye automáticamente a 360M. El caso del commit sí identifica Qwen1.5 1.8B.

## Diferencias que quedan por validar en IsyMotron

- iSyCodeMovil conserva el contexto del modelo entre respuestas; el plugin Capacitor de IsyMotron crea y destruye el contexto en cada generación. Medir la carga repetida antes de cambiar su ciclo de vida.
- iSyCodeMovil tiene presupuesto de memoria (`GUSDeviceBudget`), diagnóstico (`GUSFlightRecorder`) y benchmark físico (`GUSBenchmark`). Se pueden adaptar las partes necesarias, conservando su procedencia.
- El wrapper iOS de IsyMotron recoge estadísticas del bridge pero actualmente devuelve solo texto. Es posible exponer métricas limitadas para comparar el comportamiento sin registrar mensajes.
- Las apps tienen diferentes UI, empaquetado, prompts y límites. El antecedente físico orienta la integración; la build de IsyMotron todavía requiere una repetición en el mismo teléfono.
- La capa de herramientas del miniagente de iSyCodeMovil no se porta con el motor: GUS de IsyMotron conserva su rol de orientación y la PC mantiene la autoridad.

## Cambio al roadmap

GUS offline tiene un antecedente físico concreto; el bloque se redefine como **validación de la integración Capacitor y regresiones**, priorizando Qwen2.5 0.5B y el Smol ya usado. No hace falta investigar un motor nuevo ni esperar a un nuevo modelo NVIDIA. Se incorpora el caso Don Zelaya como prueba de repetición sin usarlo como única medida de exactitud factual.
