# GUS — instrucciones para agentes

Estas reglas aplican al código de GUS en `mobile/src/gus/`.

- Lee `ROL.md` antes de cambiar la conducta conversacional. Ese archivo es la única fuente del prompt de sistema y se empaqueta directamente en la app.
- `contracts.ts` debe importar el rol desde `ROL.md?raw`; no copies el prompt en TypeScript ni mantengas versiones distintas para los proveedores local y remoto.
- Conserva los límites de autoridad: GUS da orientación y no puede usar Link, herramientas, archivos, permisos ni actuar en la PC enlazada.
- No muestres razonamiento interno. Si hace falta explicar una respuesta, ofrece una justificación breve y útil, no una cadena de pensamiento.
- Mantén las respuestas en el idioma de la persona y tan breves como permita la pregunta. GUS no debe afirmar que hizo algo que no ejecutó.
- Al cambiar el rol, actualiza `mobile/tests/gus-role.test.ts` y verifica la suite y el build de `mobile/`.
- No añadas solicitudes remotas ni acceso a capacidades del host como parte del prompt. El enrutamiento local/remoto y la autoridad de Link son límites separados.
