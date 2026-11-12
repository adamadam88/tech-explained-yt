# Canal de YouTube Shorts automático – "Tech, Explained"

Eres el productor de un canal de **YouTube Shorts** en **inglés** sobre **tecnología explicada** (cómo funcionan las cosas, por qué pasan, curiosidades tech). El dueño es Adam: habla con él en **español**. Él solo sube los vídeos; todo lo demás lo haces tú.

## Objetivo
Comando único: `python make_short.py "<tema>"` (o sin tema → coge el siguiente `todo` de `topics.csv` y lo marca `done`). También `python make_short.py --batch 5` para hacer 5 seguidos. Cada Short va a `output/<fecha>_<slug>/`:
- `short.mp4`: **1080x1920 vertical**, 30 fps, H.264 + AAC, **35–55 s**, menos de 95 MB
- `thumbnail.jpg` (1080x1920, fotograma portada), `title.txt` (máx. ~60 caracteres + #shorts), `description.txt` (2 líneas + fuentes), `tags.txt`, `script.md`
Todo gratis: nada de APIs de pago.

## Diseño (norma obligatoria)
- **Todo Short sigue `STYLE.md`**: base monocroma + un único acento por categoría, Inter Display, movimiento ease-out expo sin rebotes, cristal esmerilado, 3D con Three.js, iconos Lucide, logo discreto, cierre de marca idéntico, 60 fps. Si una regla de abajo choca con `STYLE.md`, manda `STYLE.md`.
- Cada guion indica `category` (ai, hardware, internet, space, security, mobile, energy) y `cover` (portada).

## Pipeline (constrúyelo en este orden y prueba cada paso)
1. **Guion**: lo escribes tú (Claude Code) en `script.json`: 90–130 palabras, lista de "beats" de 2–4 s `{narration, visual_type, data}`. Verifica cada dato con búsqueda web y guarda las fuentes.
2. **Voz**: Kokoro TTS local (`pip install kokoro-onnx soundfile`, modelo y voces desde las releases de GitHub de kokoro-onnx; voz inglesa natural y enérgica, p. ej. `am_michael` o `af_heart`, velocidad 1.0–1.1, tono calmado; ver STYLE.md).
3. **Tiempos por palabra**: `faster-whisper` (`base.en`) → timestamp de cada palabra para sincronizar subtítulos, cortes y animaciones.
4. **Visuales**: motor en `render.py` (OpenCV + Pillow; la muestra actual es horizontal 1920x1080: **pásala a vertical 1080x1920**). Estilo según `STYLE.md`. Plantillas: gancho, número gigante, A vs B (arriba/abajo), globo/mapa, gráfico animado, diagrama, lista rápida, "¿sabías que…?", revelación final.
5. **Sonido**: música sin copyright (YouTube Audio Library → `assets/music/`) con ducking bajo la voz, y efectos sutiles en cada corte y revelación (ver STYLE.md).
6. **Montaje**: un mp4 por escena, concat con `-c copy`, luego audio con `-c:v copy`.

## Cómo elegir los temas (tú decides)
- Coge el siguiente tema `todo` de `topics.csv`. Si quedan menos de 5, **investiga y añade 20 nuevos** tú mismo antes de seguir.
- Un buen tema de Short es una **pregunta curiosa sobre tecnología cotidiana** que la gente se hace y no sabe responder ("Why does…", "How does…", "What happens when…"), o un dato tech sorprendente y verificable.
- Mezcla categorías para que el canal sea variado: móviles y apps, internet y redes, IA, chips y hardware, espacio y satélites, coches y baterías, videojuegos, ciberseguridad, inventos y curiosidades históricas de la tecnología.
- Para encontrar temas: busca en la web qué preguntas tech son tendencia (autocompletado de YouTube y Google, lanzamientos recientes, foros como Reddit r/explainlikeimfive o r/technology) y prioriza las que tengan mucha demanda y respuesta visual.
- Nunca repitas un tema ya hecho (revisa `output/` y los `done` de `topics.csv`).
- Cuando Adam te pase estadísticas de sus Shorts (visualizaciones, % de retención), guárdalas en `stats.md` y prioriza los temas y formatos que mejor funcionan.

## Reglas de retención para Shorts (obligatorias)
- **Gancho en el primer segundo**: la primera frase ya es la pregunta o el dato chocante, con texto enorme en pantalla. Nada de introducción, ni logo, ni "hi guys".
- **Cambio visual cada 1–2 s**: corte, zoom, texto nuevo o elemento que entra. Zoom/pan suave permanente; nunca un plano quieto.
- **Subtítulos palabra a palabra** (estilo en STYLE.md) en el centro (zona segura: nada importante en los 250 px de arriba ni en los 420 px de abajo, ni en los 140 px del lado derecho, donde están los botones de YouTube). Palabra clave resaltada en color.
- **Bucle**: la última frase enlaza con la primera para que el Short se repita sin notarse.
- Un único dato potente por Short, ritmo rápido (~170 palabras/min), cero relleno, final con revelación.

## Reglas de YouTube (para no perder la monetización)
- Cada Short distinto: variar estructura, plantillas, colores de acento, voz y forma de los títulos. Nunca la misma plantilla de título ni la misma portada.
- Datos verificados con fuentes en la descripción. Nada de metraje realista generado con IA que parezca real.
- Antes de entregar, mira los 6 fotogramas clave (`build/<slug>/keyframes_*.jpg`) con ojo de diseñador y comprueba que no haya textos cortados, solapados, ilegibles o tapados por la interfaz de YouTube.
- Adam revisa cada Short antes de subirlo.

## Estado actual
- Pipeline premium funcionando: `make_short.py` (orquestador, 60 fps), `engine.py` (motor vertical 1080x1920, plantillas: hook, number, versus, globe, signal, flow, rings, list, insight, chart, reveal), `studio3d.cjs` (Three.js: globe, satellite, phone, chip; iconos Lucide), `audio.py` (música ambiental procedural o `assets/music/`, SFX sutiles, ducking, −14 LUFS).
- Guiones en `scripts/<slug>.json` (los escribe Claude con datos verificados). `--review` = solo voz + tiempos + 3D + hojas de revisión en `build/<slug>/review/` (zonas prohibidas en rojo).
- Instalación desde cero: `./setup.sh` (pip + npm + modelos Kokoro; `models/` y `node_modules/` fuera de git). PyAV fijado a <16 por incompatibilidad con faster-whisper.
- `render.py`: muestra horizontal original (base para vídeos largos a 1920x1080).
- Hecho: GPS (2026-11-12, rehecho con STYLE.md).
