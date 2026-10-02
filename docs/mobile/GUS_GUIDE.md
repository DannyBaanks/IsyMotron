# Guía de GUS en IsyMotron Móvil

GUS conversa y orienta. No puede usar Link, leer archivos o permisos, ni mandar tareas a tus PCs. Los chats viven solo en la sesión actual de la app; al salir o borrar la conversación, se pierden.

## Usar un modelo en el teléfono

Abre **Inicio → Abrir GUS · asistente** y deja seleccionado **En este teléfono**. Elige un modelo con **Descargar y verificar**. La descarga va desde una URL fijada a una revisión concreta y la app comprueba tamaño y SHA-256 antes de activarlo. Si se cancela o falla la verificación, el modelo previo sigue disponible.

Nemotron 3 Nano 4B Q4_K_M es una opción local experimental de NVIDIA:

- Descarga aproximada de 2.84 GB. Deja espacio libre adicional, especialmente al sustituir un modelo: la app conserva el anterior hasta verificar la nueva copia.
- NVIDIA lista inglés y código como usos lingüísticos; español no aparece en su lista. La calidad en español queda **NOT_DEMONSTRATED**.
- Aunque el modelo anuncie una ventana mayor, IsyMotron limita la conversación a 2,048 tokens y la respuesta a 160 tokens.
- NVIDIA lo orienta a Jetson Thor, GeForce RTX y DGX Spark. Velocidad, memoria, batería y temperatura en teléfonos quedan **NOT_DEMONSTRATED**. Empieza con una sesión corta y detén la generación si el teléfono se calienta.

Los otros GGUF del catálogo son más pequeños. Revisa la tarjeta de cada modelo para consultar tamaño, procedencia y licencia antes de descargarlo.

## Guardar una copia y restaurarla

Con un modelo instalado, pulsa **Guardar copia externa** y elige una ubicación en el selector del sistema, por ejemplo Archivos/iCloud Drive, Google Drive o una carpeta compartida. Esa copia la administra el proveedor que elegiste; al desinstalar la app, el archivo externo permanece mientras tú o el proveedor no lo borren.

Después de reinstalar, abre GUS y pulsa **Importar copia guardada con iSyCode**. Selecciona el GGUF exportado. La app reconoce el modelo por el catálogo y verifica su tamaño y hash antes de ponerlo en la lista disponible. Si cambiaste de proveedor o de teléfono, vuelve a dar acceso mediante el selector.

Si cancelas el selector o el proveedor revoca el acceso, no se reemplaza el modelo instalado. Vuelve a importar o exportar y elige un archivo o destino accesible. Si la app rechaza una copia, conserva el archivo externo y vuelve a exportar desde la instalación que aún tenga el modelo verificado.

## NVIDIA NIM y otros proveedores remotos

El modo remoto está separado del modo local. Pulsa **Proveedor remoto** o **Usar preset NVIDIA NIM**, guarda la URL/modelo y una API key, y luego envía el mensaje. El preset configura `https://integrate.api.nvidia.com/v1` y `nvidia/nemotron-3-nano-30b-a3b`; no hace peticiones por sí solo. La key se guarda en Keychain (iOS) o almacenamiento cifrado con Android Keystore.

Al enviar en modo remoto, el mensaje y el contexto de esa conversación salen del teléfono al proveedor elegido. No se envían datos de Link, permisos ni archivos de las PCs. Las respuestas HTTP con error, incluido HTTP 202 pendiente, se muestran como error; no se consulta automáticamente otro proveedor ni se vuelve al modelo local. Para regresar al teléfono, elige **En este teléfono**.

En un navegador/PWA, los modelos y el guardado seguro remoto no están disponibles; GUS indica que se requiere la app nativa y no cambia a remoto por su cuenta.

## Comprobaciones para desarrollo

Desde `mobile/`:

```sh
npm ci
node tools/sync-gus-runtime.mjs --verify
node tools/generate-gus-catalog.mjs --check
npm test
npm run build
npx playwright install chromium
npm run e2e:gus
```

La suite de GUS simula descargas y el endpoint remoto. Asegura que una falla local no inicia una petición remota y que NIM solo recibe una petición tras elegir remoto y pulsar **Enviar**. La respuesta de NIM es simulada; no usa una API key real. `npm run build` verifica además que el mock de E2E no llegue a los assets de producción.

En CI se compilan el APK y el IPA sin firmar, se comprueba que ninguno contenga archivos `.gguf`, y se ejecutan las pruebas del almacén nativo. Una compilación exitosa no demuestra inferencia física: prueba en un iPhone y un Android la descarga, modo avión, exportación, reinstalación, importación y selección remota. Publica como **NOT_DEMONSTRATED** cualquier prueba que no hayas ejecutado en el dispositivo.
