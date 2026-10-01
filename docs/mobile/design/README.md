# IsyMotron Móvil — propuestas de UI (2026-10-01)

Dos propuestas para las 6 pantallas, con el contenido real de la app en español.
Son **inspiradas en** la estética de NVIDIA y de Nebius, **no copias**: no usan sus logos, nombres ni marcas.

- **A · Verde terminal** (`propuesta-a-*.png`): negro, verde intenso, esquinas rectas, rejilla técnica, mayúsculas.
- **B · Nube** (`propuesta-b-*.png`): azul profundo con brillo violeta, lima como acento, vidrio redondeado, botones píldora.

Pantallas: 1 Inicio · 2 Enlazar (dirección) · 3 Enlazar (código) · 4 Mi PC · 5 Recibos (nueva) · 6 Este teléfono (nueva).
Navegación inferior nueva: Inicio, Tareas, Recibos, Teléfono.

Fuente editable: `mockups.html` (`#a` o `#b` en la URL). Se renderiza a PNG con Playwright.

## Inicio con Malbolgato (prototipo interactivo)

`home-malbolgato.src.html` + `build_home.py`: la pantalla de inicio en Verde terminal con Malbolgato y sus
6 animaciones del Companion (`avatar/packs/malbolge-cat`). Toca = reacción; mantener = controles (como el clic
derecho del avatar de escritorio). Mismas reglas que `docs/AVATAR_CONTRACT.md`: el marco verde o rojo solo viene
de una PC firmada; cualquier otro texto sale como tercero no verificado; Malbolgato no tiene autoridad.

    python3 docs/mobile/design/build_home.py /tmp/inicio-malbolgato.html
