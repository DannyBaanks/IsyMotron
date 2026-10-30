# IsyMotron: alcance de entrega para el 30 de octubre

Fecha: 2026-10-21. Estado: alcance solicitado por el usuario; planificación, sin implementación nueva en este documento.

## Objetivo confirmado

El usuario solicita corregir los hallazgos de la auditoría y preparar una entrega usable para el hackathon que cierra el **30 de octubre de 2026**. Eligió **PC + app móvil como flujo principal y web como panel de control**. Hay un **iPhone 12 físico** para probar GUS con modelos pequeños.

“Usable” significa que una persona puede instalar, enlazar el iPhone con una PC, conversar localmente con GUS, enviar explícitamente una tarea a la PC, aprobar o rechazar una solicitud y comprobar el resultado. Un error tiene explicación y recuperación. Los indicadores de autoridad y evidencia coinciden con el host.

El periodo de construcción es 21–27 de octubre; demo y entrega inicial, 28; contingencia, 29. La hora y zona oficiales del cierre siguen por confirmar. Las fechas son objetivos de trabajo, no garantías de duración.

**Antecedente confirmado el 21 de octubre:** el usuario ya obtuvo respuestas en modo avión en iSyCodeMovil con Qwen 0.5B, Smol y otro Qwen. El caso histórico «Don Zelaya», commit `bea62f4`, identifica una prueba física con Qwen1.5 1.8B. IsyMotron ya incluye el mismo bridge C y la misma revisión de llama.cpp, y hereda la corrección de repetición de ese caso. El trabajo es validar la integración de ese motor en IsyMotron. Véase [comparación y procedencia](../../audits/2026-10-21-manus/GUS_ISYCODE_REUSE.es.md).

## Arquitectura conservada

- La PC evalúa grants, perfiles, scopes y leases y ejecuta mediante el enforcer existente.
- Link conserva autenticación, cifrado y respuestas selladas. El envío de una tarea es una acción explícita de la persona. El modelo GUS no recibe acceso a Link ni herramientas.
- GUS local usa el runtime llama.cpp ya fijado y el catálogo verificado. Remoto es una elección explícita, con credenciales en almacenamiento nativo; un fallo local no inicia una petición remota.
- El panel web lee una proyección autenticada del estado. No se convierte en un segundo ejecutor ni recibe el token privado de la PC.
- La evidencia del runner y la de la consola tienen orígenes identificables. Un recibo de transporte no equivale a un recibo de ejecución. Si se unifican en el panel, se verifica cada tipo y se conserva su procedencia.

## Requisitos de entrega

1. Una revisión de integración contiene el panel de `master`, las mejoras móviles y los componentes locales revisados necesarios para ejecutar tareas; un manifiesto identifica sus commits.
2. El panel rechaza acceso no autenticado al estado real y no entrega resultados privados, secretos ni rutas físicas innecesarias.
3. `ALLOW`, ejecución y sello verificado son estados diferentes. Fechas, identidad de host, disponibilidad y límites de capabilities vienen del contrato real; lo ausente se muestra como desconocido.
4. El panel actualiza datos cada 5 segundos mientras está visible, con una sola petición activa y sin sobrescribir respuestas nuevas con antiguas. Marca la vista como desactualizada a los 15 segundos sin actualización y comprueba de nuevo al volver del segundo plano.
5. La carga de GUS respeta la navegación y tiene recuperación tras fallo de descarga/import. Un chunk que exige recarga ofrece recargar de forma explícita.
6. Las tareas tienen estados terminales honestos, timeout visible y cancelación. Reintentos o reinicios no repiten una ejecución ya completada. Se comprueba la concurrencia entre servidor Link y runner antes de integrar este último.
7. El iPhone 12 instala y abre la build final; conserva la identidad al cerrar y abrir; rechaza pairing incorrecto; completa el flujo permitido y el rechazado con una PC real.
8. Al menos un modelo pequeño genera respuestas localmente en modo avión en el iPhone 12. Descarga/importación, hash inválido, cancelar, borrar modelo y recuperación por falta de espacio tienen resultados explícitos.
9. Se registran latencia, tiempo total, contexto, salida, errores y estado térmico observable del modelo. Se evalúan 10 prompts de orientación en español y se conserva el resultado. Objetivo inicial: al menos 8 respuestas útiles y ninguna afirmación falsa de haber ejecutado acciones; si no se cumple, se ajusta el modelo o se reduce el alcance anunciado.
10. Un checkout limpio reproduce pruebas y builds; la revisión de la app coincide con la del host usado en la demo. Las afirmaciones sobre hardware solo se marcan demostradas tras su prueba física.

## Modelos y alcance del experimento NVIDIA

El catálogo ya contiene SmolLM2 360M Q4_K_M (270,590,528 bytes) y Qwen2.5 0.5B Instruct Q4_K_M (491,400,032 bytes). Se prueban primero en el iPhone y se elige por evidencia física. Contexto inicial de prueba: 512; después 1,024 y hasta 2,048 si es estable. La prueba de respuesta comienza en 64 tokens y conserva el límite actual máximo de 160.

Ambos artefactos coinciden por SHA-256 con los del catálogo de iSyCodeMovil. Priorizar reproducir la combinación que ya usó el usuario. La variante exacta de Smol se identifica al repetir la prueba; Qwen1.5 1.8B es el del caso histórico, pero no se añade automáticamente al catálogo de IsyMotron. Comparar el ciclo de vida del contexto y adaptar medición de memoria/tiempos cuando resuelva un problema observado, manteniendo los límites de autoridad actuales.

La ficha oficial de [Nemotron 3.5 Embed 1B](https://huggingface.co/nvidia/Nemotron-3.5-Embed-1B-BF16) declara lanzamiento el 20 de octubre y salida de embeddings. Ese candidato sirve para recuperación/búsqueda y no cubre la necesidad generativa de GUS. No se incorpora al catálogo de chat.

Existe además [Nemotron Flash 1B](https://huggingface.co/nvidia/Nemotron-Flash-1B), cuya ficha describe un modelo base con arquitectura propia e instrucciones de ejecución CUDA. Esa ficha no demuestra compatibilidad con el runtime iOS fijado. Si el usuario se refiere a otro lanzamiento, se evalúa por su identificador exacto antes de decidir. El experimento de un nuevo modelo generativo tiene un máximo de 2 horas de investigación inicial y una decisión antes del 25 de octubre; no bloquea los arreglos ni exige portar un runtime nuevo para esta entrega.

## Límites de alcance

- Web: sesión, monitor, equipos, capacidades y evidencia; el chat web completo se pospone conforme a la elección del usuario.
- Plataforma física prioritaria: iPhone 12 y una PC real disponible. Se registra el sistema operativo exacto de esa PC al comenzar. Android y otros escritorios conservan los checks existentes, sin prometer pruebas físicas no realizadas.
- Nemotron local de 4B, integración de TamagotchIA, marketplace nuevo, sincronización multiusuario y rediseños generales quedan fuera del camino crítico.
- Ninguna publicación de release, despliegue o envío del hackathon se hace solo por aparecer como tarea en este documento. Se prepara la entrega para su revisión y ejecución autorizada.

## Evidencia y dependencias

Entrada principal: [auditoría del 21 de octubre](../../audits/2026-10-21-manus/REPORT.es.md).

Dependencias inmediatas: método de firma/instalación del IPA, versión de iOS, PC de prueba, conectividad local, acceso a un proveedor permitido por el hackathon y hora oficial de cierre. La instalación física y la validación de proveedor se prueban desde el primer día.

Se encontró trabajo adicional fuera de `master` en la rama local `claude/exciting-lamport-84gclk`: runner, perfiles y TTL de sesión. Integrarlo requiere revisión específica; los resultados de la auditoría de `master` no cubren automáticamente esa combinación nueva.
