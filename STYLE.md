# STYLE.md — Sistema de diseño de Quiet Circuit (@quietcircuit) (obligatorio)

Quiet Circuit: la tecnología que nos rodea funciona en silencio; el canal la saca a la luz. Referencia: keynotes de Apple y documentales minimalistas. **Premium, limpio, elegante.** Si algo parece "plantilla de YouTube", está mal.
Implementación: `engine.py` (2D, composición, movimiento), `studio3d.cjs` (3D + iconos), `audio.py` (sonido).

## 1. Color
| Uso | Valor |
|---|---|
| Fondo | `#0A0A0A` (con un leve levantamiento radial hacia `#131313`) |
| Texto principal | `#F5F5F2` |
| Grises | `#161616` · `#2C2C2C` (líneas, barras) · `#77776F` (secundario) · `#A9A9A3` (etiquetas, iconos) |

**Un solo acento por categoría**, solo en lo importante (palabra clave, dato clave, punto "tú", barra final):

| Categoría (`category` en el guion) | Acento |
|---|---|
| `ai` — IA | `#8B7CFF` |
| `hardware` — chips/hardware | `#FFB547` |
| `internet` — internet/redes | `#4DA3FF` |
| `space` — espacio/satélites | `#5CE1E6` |
| `security` — ciberseguridad | `#FF5A5A` |
| `mobile` — móviles/apps | `#7CFFB2` |
| `energy` — energía/baterías | `#D4FF3A` |

Si el guion no indica categoría, `engine.guess_category()` la deduce del tema. Nunca dos acentos en un Short.

## 2. Tipografía
- **Inter Display** (Geist no está instalada; Inter Display es la elegida).
- Titulares: SemiBold, enormes, tracking −3,5 %. Números gigantes: SemiBold, tracking −4,5 %, la unidad en pequeño y gris.
- Secundarios: Medium, pequeños (22–30 px), MAYÚSCULAS con tracking +20 %, en gris.
- **Máximo 3–5 palabras en pantalla por plano** (sin contar subtítulos). Usa `|` para partir líneas.

## 3. Movimiento
- Easing **ease-out expo** (`1 − 2^(−10x)`). Sin rebotes, sin overshoot, sin sacudidas, sin escalados "pop".
- Entradas: **fade + desenfoque que se enfoca + desplazamiento de ~30 px hacia arriba** (`engine.enter`), con escalonado de 60–70 ms entre palabras.
- Cámara: push-in o pull-back lento y constante (3 %) con deriva lateral mínima; nunca un plano quieto.
- Cortes limpios entre planos (cada 1–2 s pasa algo: corte, elemento que entra o cambio de plano dentro del beat).
- **Cierre de marca idéntico en todos los vídeos**: últimos 0,85 s → desenfoque + fundido a `#0A0A0A` y el símbolo de Quiet Circuit se dibuja y su nodo se enciende (ver sección 10). Después vuelve el gancho (bucle).

## 4. Profundidad
- Capa de **bokeh desenfocado** que deriva despacio + resplandor suave del acento detrás del protagonista.
- **Paneles de cristal esmerilado** (`engine.glass`): fondo desenfocado, tinte 5 %, brillo superior, borde fino 1,5 px, sombra suave.
- Sombras suaves bajo el texto sobre imagen. **Viñeta sutil** y **grano de película muy ligero** en todo el fotograma.

## 5. 3D
- Objetos protagonistas con **Three.js** (`studio3d.cjs`, Chromium sin pantalla): `globe` (globo de puntos con costas reales de Natural Earth + órbitas), `satellite`, `phone`, `chip`, `battery` (celda pouch de aluminio), `router` (cúpula de malla con anillo de luz).
- Iluminación de estudio (RoomEnvironment + key light + rim light del color de acento), tone mapping ACES, giro lento y continuo entre cortes.
- Materiales sobrios: metal, cristal oscuro. Nada de colores saturados en superficies grandes.
- Para añadir un objeto: nueva función en `studio3d.cjs` y registrarla en `BUILD`.

## 6. Iconos
- **Solo Lucide** (`lucide-static`), trazo uniforme de **3 px** a cualquier tamaño (`ICON_STROKE`), en gris `#A9A9A3` o en acento si es lo importante.

## 7. Subtítulos
- Blancos `#F5F5F2`, **Inter Display Medium 72 px**, centrados en la zona segura (y = 1345), máx. 3 palabras.
- Palabra clave (`*así*` en la narración) en el color de acento. Aparición suave palabra a palabra (fade + blur + 12 px).
- Sin cajas, sin contornos gruesos: solo una sombra difusa.

## 8. Zona segura (YouTube Shorts)
Nada importante en los 250 px de arriba, los 420 px de abajo ni los 140 px de la derecha. El contenido se centra en x = 500.

## 9. Sonido
- Música **ambiental / electrónica minimalista** (pads lentos, sub suave, plucks con reverb, kick de fieltro). Original y sin copyright; o pistas propias en `assets/music/`.
- Efectos sutiles: `swish` en cortes, `tick` en elementos, `chime` en el dato clave, `rise` antes de la revelación.
- Voz **calmada**: por defecto `af_heart` (la mejor valorada de Kokoro) a 1,05. Alternativas probadas: `af_bella`, `am_fenrir`, `am_puck`, `am_michael`, `bf_emma`. Varía la voz entre Shorts.
- Mezcla a −14 LUFS con ducking de la música bajo la voz.

## 10. Marca (ver `branding/README.md`)
- **Símbolo "Filament"**: una Q de circuito — anillo + una pista PCB (45° → horizontal) que acaba en un **nodo encendido**. Geometría única
  compartida por `branding/brandkit.py` y `engine.py` (`MARK_*`). No deformar, no añadir efectos, no recolorear el anillo.
- **Logotipo de texto**: "Quiet" Inter Display Light gris + "Circuit" SemiBold blanco. En tamaños pequeños: `QUIET CIRCUIT` Medium/SemiBold, tracking +24 %.
- **Color de marca**: monocromo + **Filament `#FFE7B8`** solo en el nodo (perfil, banner, marca de agua). **En los vídeos, el nodo usa el acento de la categoría.**
- **En cada Short**: logo de esquina discreto (símbolo de 34 px + `QUIET CIRCUIT` 21 px, gris) arriba a la izquierda, dentro de la zona segura.
- **Cierre idéntico en todos los vídeos** (0,85 s, `engine.outro`): la escena se desenfoca y funde a `#0A0A0A`, el símbolo se dibuja solo
  (anillo → pista), el nodo se enciende con un `chime` suave y aparece `QUIET CIRCUIT`. Luego el bucle vuelve al gancho.
- **Portadas** con el mismo esquema: logo de esquina, etiqueta pequeña, titular de 2–4 palabras (palabra clave en acento) y el objeto 3D debajo.
- Recursos del canal en `branding/`: perfil 800x800, banner 2560x1440 (contenido dentro de 1546x423), marca de agua 150x150.

## 11. Calidad
1080x1920, **60 fps**, H.264 High (CRF 16, máx. 22 Mb/s), AAC 256 kb/s, **< 95 MB**.

## 12. Control de calidad antes de entregar
`make_short.py` extrae **6 fotogramas clave** del mp4 final (`build/<slug>/keyframes_*.jpg`). Revísalos con ojo de diseñador:
textos cortados o solapados, algo bajo la interfaz de YouTube, más de 5 palabras por plano, colores fuera de la paleta, objetos 3D quemados o
demasiado saturados, composición desequilibrada. Corrige y vuelve a renderizar antes de entregar.
