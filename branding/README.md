# Quiet Circuit — identidad de marca

**Canal:** Quiet Circuit · **Handle:** @quietcircuit · **Lema:** *The quiet tech around you, brought to light.*

## Concepto: "Filament"
El símbolo es una **Q dibujada como un circuito**: un anillo cerrado (la tecnología que funciona en silencio, encerrada en sí misma)
del que sale **una sola pista de circuito impreso** (45° y luego en horizontal) que termina en **un nodo encendido**.
Ese nodo es la idea del canal: sacar a la luz lo que no se ve. Es la única parte con luz y color de toda la marca.

- **Logotipo de texto:** "Quiet" en Inter Display *Light* gris + "Circuit" en *SemiBold* blanco. El peso de la letra cuenta el nombre:
  lo silencioso es fino y apagado; el circuito, firme y visible.
- **Color de marca:** monocromo (`#0A0A0A` / `#F5F5F2` / grises de STYLE.md) + **Filament `#FFE7B8`**, un blanco cálido de bombilla,
  usado solo en el nodo. Dentro de los vídeos, el nodo toma el **acento de la categoría** del Short ("la luz cambia con el tema").
- **Por qué funciona:** es propio y no genérico (no es una lupa, ni un chip, ni una onda), se reconoce a 32 px, es un solo trazo
  (anima de forma natural en el cierre) y une el nombre (Q + circuito) con el propósito (la luz).

## Archivos
| Archivo | Uso |
|---|---|
| `logo/quietcircuit-logo-dark.svg/.png` | Logo principal (símbolo + nombre) sobre negro |
| `logo/quietcircuit-logo-light.svg/.png` | Versión sobre fondo claro (sin halo) |
| `logo/quietcircuit-logo-transparent.svg/.png` | Logo con fondo transparente |
| `logo/quietcircuit-mark*.svg/.png` | Símbolo solo: color de marca, blanco y negro |
| `logo/quietcircuit-wordmark-caps.svg/.png` | Versión en mayúsculas espaciadas para tamaños pequeños |
| `profile_800.png` | **Foto de perfil** de YouTube (800x800; símbolo centrado ópticamente dentro del círculo) |
| `banner_2560x1440.jpg` / `.png` | **Banner** (logo y lema dentro de la zona segura de móvil 1546x423; pistas decorativas fuera) |
| `watermark_150.png` | **Marca de agua** de YouTube (150x150, transparente, con sombra suave para fondos claros) |
| `options/` | Exploración: 5 conceptos de símbolo, 3 de logotipo de texto, 4 afinados de color y tamaño, vista de zonas del banner |

Todo es vectorial y reproducible: `python branding/brandkit.py explore` (opciones) y `python branding/brandkit.py final`
(recursos finales). El texto se convierte en trazos con HarfBuzz (kerning real de Inter Display) y Chromium rasteriza los SVG.
La geometría del símbolo es la misma en `brandkit.py` (`mark_B`) y en `engine.py` (`MARK_*`).

## Subir a YouTube (YouTube Studio → Personalización → Branding)
1. **Imagen** → `profile_800.png`. 2. **Imagen del banner** → `banner_2560x1440.jpg`. 3. **Marca de agua del vídeo** → `watermark_150.png`
   (mostrar "al final del vídeo" o "todo el vídeo"; el cierre de cada Short ya incluye la firma animada).
