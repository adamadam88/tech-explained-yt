# Canal de YouTube automático – "Tech, Explained"

Eres el productor de un canal de YouTube en **inglés** sobre **tecnología explicada** (cómo funcionan las cosas, por qué pasan, curiosidades tech). El dueño es Adam: habla con él en **español**. Él solo sube los vídeos; todo lo demás lo haces tú.

## Objetivo
Comando único: `python make_video.py "<tema>"` (o sin tema → coge el siguiente de `topics.csv`) produce en `output/<fecha>_<slug>/`:
- `video.mp4` (1920x1080, 30 fps, H.264 + AAC, 6–10 min) y opcional `short.mp4` (1080x1920, <60 s)
- `thumbnail.jpg` (1280x720), `title.txt`, `description.txt` (con fuentes), `tags.txt`, `script.md`
Todo gratis: nada de APIs de pago.

## Pipeline (constrúyelo en este orden y prueba cada paso)
1. **Guion**: lo escribes tú (Claude Code) en `script.json`: lista de escenas `{narration, visual_type, data}`. Verifica cada dato con búsqueda web y guarda las fuentes.
2. **Voz**: Kokoro TTS local (`pip install kokoro-onnx soundfile`, descarga modelo y voces; voz inglesa masculina o femenina natural, p. ej. `am_michael` o `af_heart`). Una pista por escena.
3. **Tiempos por palabra**: `faster-whisper` (modelo `base.en`) sobre cada pista → timestamps de cada palabra para sincronizar textos y cortes.
4. **Visuales**: motor en `render.py` (OpenCV + Pillow, dibujado a 1080p, ya hay una muestra funcionando con estilo oscuro navy/cian/naranja y fuente Inter). Añade plantillas reutilizables: título-gancho, número gigante, comparación A vs B, mapa/globo, gráfico animado, línea del tiempo, diagrama de flujo, lista top‑N, cita/titular, "pregunta abierta".
5. **Sonido**: música de fondo sin copyright (YouTube Audio Library, carpeta `assets/music/`) con ducking bajo la voz (-18 dB) y efectos (whoosh, pop, click) en cada transición, generados o de librerías CC0.
6. **Montaje**: un mp4 por escena, concat con `-c copy`, luego audio con `-c:v copy` (reglas de la skill de vídeo). Subtítulos quemados palabra a palabra.
7. **Miniatura + metadatos**: miniatura con 2–4 palabras enormes, alto contraste, un elemento visual; título con curiosidad (sin clickbait falso).

## Reglas de retención (obligatorias)
- **Gancho en los primeros 5 s**: pregunta o dato sorprendente + promesa de lo que se va a descubrir. Nada de "Hi guys, welcome".
- **Algo cambia en pantalla cada 2–4 s**: zoom/pan suave constante (Ken Burns), cortes, textos que entran palabra a palabra sincronizados con la voz.
- **Bucles abiertos**: anunciar algo que se revela más adelante ("but the strangest part comes at the end").
- **Escenas de 8–20 s**, interrupciones de patrón cada ~30 s (cambio de color de fondo, plantilla distinta, efecto de sonido).
- **Barra de progreso** fina arriba y capítulos en la descripción.
- Frases cortas en la narración, ritmo ~160 palabras/min, cero relleno.
- Final rápido: conclusión + siguiente vídeo recomendado, sin despedidas largas.

## Reglas de YouTube (para no perder la monetización)
- Cada vídeo distinto: variar estructura, plantillas, colores de acento y miniaturas. Nunca títulos con la misma plantilla.
- Datos verificados y fuentes en la descripción. Nada de metraje realista generado con IA que parezca real.
- Antes de entregar, mira fotogramas clave (lee los JPG) y comprueba que no haya textos cortados, solapados o ilegibles.
- Adam revisa cada vídeo antes de subirlo.

## Estado actual
- `render.py`: motor de muestra (vídeo GPS de 42 s sin voz) → base para las plantillas.
- Pendiente: todo el pipeline anterior. Empieza instalando dependencias (`ffmpeg`, Python 3.10+), luego voz, luego plantillas, y genera un primer vídeo completo de prueba.
