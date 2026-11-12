"""Quiet Circuit brand kit: vector mark + wordmark (text outlined with HarfBuzz shaping) -> SVG, rasterized by Chromium.

    python branding/brandkit.py explore   # concept options + comparison boards in branding/options/
    python branding/brandkit.py final     # final logo / profile / banner / watermark in branding/
"""
import json, math, os, subprocess, sys
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
FD = "/usr/share/fonts/opentype/inter/"
BG, INK, G3, G4 = "#0A0A0A", "#F5F5F2", "#77776F", "#A9A9A3"
FILAMENT = "#FFE7B8"                  # brand light: warm "filament" white — the quiet tech, brought to light
LIGHT = FILAMENT

# ---------------------------------------------------------------- type → outlined SVG paths
_FACES = {}
def _face(weight, display=True):
    key = (weight, display)
    if key not in _FACES:
        p = FD + (f"InterDisplay-{weight}.otf" if display else f"Inter-{weight}.otf")
        f = hb.Font(hb.Face(hb.Blob.from_file_path(p))); tt = TTFont(p)
        _FACES[key] = (f, tt, tt.getGlyphSet(), tt.getGlyphOrder(), tt["head"].unitsPerEm)
    return _FACES[key]

def text_path(s, weight, size, x, y, track=0.0, anchor="start", display=True):
    """Outlined text (kerned by HarfBuzz). track in em. Returns (svg path d, advance width)."""
    f, tt, gs, order, upem = _face(weight, display)
    buf = hb.Buffer(); buf.add_str(s); buf.guess_segment_properties(); hb.shape(f, buf, {"kern": True, "liga": True})
    sc = size / upem; adv = [p.x_advance + track * upem for p in buf.glyph_positions]
    width = (sum(adv) - track * upem) * sc
    x0 = x - {"start": 0, "middle": width / 2, "end": width}[anchor]; pen = SVGPathPen(gs); cx = 0.0
    for info, pos, a in zip(buf.glyph_infos, buf.glyph_positions, adv):
        tp = TransformPen(pen, (sc, 0, 0, -sc, x0 + (cx + pos.x_offset) * sc, y - pos.y_offset * sc))
        gs[order[info.codepoint]].draw(tp); cx += a
    return pen.getCommands(), width

def cap_height(weight, size, display=True):
    tt = _face(weight, display)[1]; return tt["OS/2"].sCapHeight / tt["head"].unitsPerEm * size

# ---------------------------------------------------------------- marks (100-unit box, centred on 50,50)
def _pad(x, y, r, color, glow):
    g = f'<circle cx="{x}" cy="{y}" r="{r * 2.6}" fill="{color}" opacity="{0.55 * glow}" filter="url(#glow)"/>' if glow else ""
    return g + f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'

def mark_A(ink, light, sw=7.0, glow=1.0):        # Q-trace, straight diagonal tail
    c, r = (45, 45), 29; a = math.radians(45)
    p0 = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
    return (f'<circle cx="{c[0]}" cy="{c[1]}" r="{r}" fill="none" stroke="{ink}" stroke-width="{sw}"/>'
            f'<path d="M{p0[0]:.2f} {p0[1]:.2f} L76 76" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" fill="none"/>'
            + _pad(82, 82, 6.2, light, glow))

# Final mark geometry (shared with engine.py `MARK`): ring c=(44,46) r=29, tail 45°→(72,74)→(83,74), pad (89,74) r=6.2
def mark_B(ink, light, sw=7.0, glow=1.0):        # Q-trace PCB tail: 45° then horizontal, ending on a lit pad
    c, r = (44, 46), 29; a = math.radians(45)
    p0 = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
    halo = f'<circle cx="89" cy="74" r="13" fill="{light}" opacity="{0.42 * glow}" filter="url(#glow)"/>' if glow else ""
    return (halo + f'<circle cx="{c[0]}" cy="{c[1]}" r="{r}" fill="none" stroke="{ink}" stroke-width="{sw}"/>'
            f'<path d="M{p0[0]:.2f} {p0[1]:.2f} L72 74 L83 74" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            f'<circle cx="89" cy="74" r="6.2" fill="{light}"/>')

def mark_C(ink, light, sw=6.0, glow=1.0):        # silent signal: flatline with one pulse inside a ring
    return (f'<circle cx="50" cy="50" r="38" fill="none" stroke="{ink}" stroke-width="{sw}"/>'
            f'<path d="M22 50 H42 L48 38 L54 62 L58 50 H66" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
            + _pad(74, 50, 5.2, light, glow))

def mark_D(ink, light, sw=None, glow=1.0):       # dot matrix, one node lit
    out = []
    for i in range(5):
        for j in range(5):
            x, y = 18 + i * 16, 18 + j * 16
            if math.dist((x, y), (50, 50)) > 36: continue
            out.append(_pad(x, y, 5.2, light, glow) if (i, j) == (3, 3) else f'<circle cx="{x}" cy="{y}" r="4.2" fill="{ink}" opacity=".9"/>')
    return "".join(out)

def mark_E(ink, light, sw=7.0, glow=1.0):        # open loop: a ring with one quiet gap, closed by a lit node
    c, r, gap = (50, 50), 32, 42                  # gap (degrees) centred at 0° (3 o'clock)
    a0, a1 = math.radians(gap / 2), math.radians(360 - gap / 2)
    p0 = (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0)); p1 = (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))
    return (f'<path d="M{p0[0]:.2f} {p0[1]:.2f} A{r} {r} 0 1 1 {p1[0]:.2f} {p1[1]:.2f}" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" fill="none"/>'
            + _pad(c[0] + r, c[1], 6.4, light, glow))

MARKS = {"A_qtrace_diagonal": mark_A, "B_qtrace_pcb": mark_B, "C_silent_pulse": mark_C, "D_dot_matrix": mark_D, "E_open_loop": mark_E}

DEFS = ('<defs><filter id="glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="{b}"/></filter>'
        '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" stitchTiles="stitch"/>'
        '<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .9 0"/></filter>'
        '<radialGradient id="lift" cx="50%" cy="46%" r="60%"><stop offset="0" stop-color="#1A1A1A"/><stop offset="1" stop-color="{bg}"/></radialGradient>'
        '<radialGradient id="halo" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{light}" stop-opacity=".16"/><stop offset="1" stop-color="{light}" stop-opacity="0"/></radialGradient>'
        '</defs>')
def defs(blur=3.2, light=LIGHT, bg=BG): return DEFS.format(b=blur, light=light, bg=bg)

def svg(w, h, body, extra_defs=""):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{extra_defs}{body}</svg>'

def place(mark_svg, x, y, size):
    """Put a 100-unit mark with its box top-left at (x, y), `size` px wide."""
    return f'<g transform="translate({x:.2f} {y:.2f}) scale({size / 100:.5f})">{mark_svg}</g>'

def grain(w, h, opacity=.035): return f'<rect width="{w}" height="{h}" filter="url(#grain)" opacity="{opacity}"/>'

# ---------------------------------------------------------------- wordmarks
def wordmark(style, size, x, y, color=INK, color2=None, anchor="start"):
    """y = baseline. Returns (svg, width)."""
    color2 = color2 or color
    if style == "weights":                       # "Quiet" Light + "Circuit" SemiBold: quiet and loud, in one name
        d1, w1 = text_path("Quiet", "Light", size, 0, 0, -.02); sp = size * .24
        d2, w2 = text_path("Circuit", "SemiBold", size, 0, 0, -.025); W = w1 + sp + w2
        x0 = x - {"start": 0, "middle": W / 2, "end": W}[anchor]
        return (f'<g transform="translate({x0:.2f} {y:.2f})"><path d="{d1}" fill="{color2}"/>'
                f'<path transform="translate({w1 + sp:.2f} 0)" d="{d2}" fill="{color}"/></g>'), W
    if style == "caps":
        d, w = text_path("QUIET CIRCUIT", "Medium", size, x, y, .2, anchor); return f'<path d="{d}" fill="{color}"/>', w
    if style == "lower":
        d, w = text_path("quiet circuit", "Medium", size, x, y, -.025, anchor); return f'<path d="{d}" fill="{color}"/>', w
    raise KeyError(style)

def lockup(mark_fn, style, mark_px, x, cy, ink=INK, light=LIGHT, quiet=G4, glow=1.0, sw=7.0):
    """Horizontal lockup centred vertically on cy, starting at x. Returns (svg, total width)."""
    size = mark_px * .5 if style != "caps" else mark_px * .3
    m = place(mark_fn(ink, light, sw, glow), x, cy - mark_px / 2, mark_px)
    gap = mark_px * .28
    wm, w = wordmark(style, size, x + mark_px + gap, cy + cap_height("SemiBold", size) / 2, ink, quiet if style == "weights" else ink)
    return m + wm, mark_px + gap + w

# ---------------------------------------------------------------- assets
def avatar(mark_fn, light=LIGHT, size=800, mark_scale=.5, sw=7.0, glow=1.0, offset=(0, 0)):
    s = size * mark_scale; x = (size - s) / 2 + offset[0] * size; y = (size - s) / 2 + offset[1] * size
    body = (f'<rect width="{size}" height="{size}" fill="{BG}"/><rect width="{size}" height="{size}" fill="url(#lift)"/>'
            + place(mark_fn(INK, light, sw, glow), x, y, s) + grain(size, size, .03))
    return svg(size, size, body, defs(3.2, light))

def rasterize(jobs):
    p = os.path.join(HERE, ".jobs.json"); json.dump(jobs, open(p, "w"))
    subprocess.run(["node", os.path.join(HERE, "rasterize.cjs"), p], check=True); os.remove(p)

def write(path, content): os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").write(content); return path

# ---------------------------------------------------------------- explore: options + comparison boards
def explore():
    from PIL import Image, ImageDraw, ImageFont
    od = os.path.join(HERE, "options"); os.makedirs(od, exist_ok=True); jobs = []
    for k, fn in MARKS.items():
        jobs.append({"svg": avatar(fn), "out": os.path.join(od, f"avatar_{k}.png"), "w": 800, "h": 800})
    for style in ("weights", "caps", "lower"):
        body, w = lockup(mark_B, style, 150, 80, 160)
        jobs.append({"svg": svg(1500, 320, f'<rect width="1500" height="320" fill="{BG}"/>' + body, defs(3.2 * 1.5)),
                     "out": os.path.join(od, f"lockup_{style}.png"), "w": 1500, "h": 320})
    rasterize(jobs)
    # board: each mark as YouTube shows it (circle crop) at 98 / 48 / 32 px on dark and light UI
    lab = ImageFont.truetype(FD + "Inter-Medium.otf", 18)
    rows = list(MARKS); cw, rh = 1100, 300
    board = Image.new("RGB", (cw, rh * len(rows)), (24, 24, 24)); d = ImageDraw.Draw(board)
    for i, k in enumerate(rows):
        av = Image.open(os.path.join(od, f"avatar_{k}.png")).convert("RGB"); y = i * rh
        d.text((20, y + 12), k, font=lab, fill=(220, 220, 210))
        x = 20
        for ui in ((15, 15, 15), (255, 255, 255)):
            d.rectangle((x - 10, y + 40, x + 500, y + rh - 20), fill=ui)
            xx = x
            for s in (220, 98, 48, 32):
                a = av.resize((s, s), Image.LANCZOS); m = Image.new("L", (s * 4, s * 4), 0)
                ImageDraw.Draw(m).ellipse((0, 0, s * 4 - 1, s * 4 - 1), fill=255); m = m.resize((s, s), Image.LANCZOS)
                board.paste(a, (xx, y + 50 + (220 - s) // 2), m); xx += s + 24
            x += 540
    board.save(os.path.join(od, "board_marks.png"))
    lk = [Image.open(os.path.join(od, f"lockup_{s}.png")) for s in ("weights", "caps", "lower")]
    b2 = Image.new("RGB", (1500, 320 * 3)); [b2.paste(im, (0, 320 * i)) for i, im in enumerate(lk)]
    b2.save(os.path.join(od, "board_wordmarks.png"))
    print("options ->", od)

# ---------------------------------------------------------------- final assets
OPT = dict(sw=8.6, glow=.85)              # optical-size settings chosen in round 2 (B3)
TAGLINE = "The quiet tech around you, brought to light"

def _traces(W, H, safe):
    """Decorative PCB traces on fixed, non-crossing lanes, entering from both edges and stopping before the
    mobile safe area (inside the 423 px band) or further in (TV-only rows). Three end pads are lit."""
    sx0, sy0, sx1, sy1 = safe; out = []
    lanes = [  # (side, y, jog_y, stop_x, lit)
        (-1, 250, 40, 980, False), (1, 300, -50, 1640, False), (-1, 1150, -45, 1100, True), (1, 1210, 35, 1500, False),
        (-1, 560, 34, sx0 - 70, False), (-1, 640, -30, sx0 - 150, False), (-1, 770, 36, sx0 - 60, True), (-1, 850, -28, sx0 - 190, False),
        (1, 585, -32, sx1 + 90, False), (1, 690, 30, sx1 + 60, True), (1, 800, -34, sx1 + 170, False), (1, 870, 26, sx1 + 80, False)]
    for side, y, jy, stop, lit in lanes:
        x0 = 0 if side < 0 else W; jx = x0 + (stop - x0) * .45
        d = f"M{x0} {y} H{jx:.0f} L{jx - side * abs(jy):.0f} {y + jy} H{stop:.0f}"
        col = "#2A2A2A"
        out.append(f'<path d="{d}" stroke="{col}" stroke-width="3" fill="none" stroke-linejoin="round"/>')
        px, py = stop - side * 7, y + jy
        if lit:
            out.append(f'<circle cx="{px:.0f}" cy="{py}" r="24" fill="{FILAMENT}" opacity=".2" filter="url(#glow)"/>'
                       f'<circle cx="{px:.0f}" cy="{py}" r="7" fill="{FILAMENT}" opacity=".85"/>')
        else:
            out.append(f'<circle cx="{px:.0f}" cy="{py}" r="7" fill="{BG}" stroke="{col}" stroke-width="3"/>')
    return "".join(out)

def banner():
    W, H = 2560, 1440; sx0, sy0 = (W - 1546) / 2, (H - 423) / 2          # mobile safe area 1546x423
    mpx = 168; size = 112
    d1, w1 = text_path("Quiet", "Light", size, 0, 0, -.02); d2, w2 = text_path("Circuit", "SemiBold", size, 0, 0, -.025)
    gap = mpx * .3; tw = mpx + gap + w1 + size * .24 + w2; x0 = W / 2 - tw / 2; cy = H / 2 - 34
    lock, _ = lockup(mark_B, "weights", mpx, x0, cy, **OPT)
    tag, _ = text_path(TAGLINE.upper(), "Medium", 25, W / 2, cy + 150, .24, "middle", display=False)
    keep = (x0 - 80, sy0, x0 + tw + 80, sy0 + 423)
    body = (f'<rect width="{W}" height="{H}" fill="{BG}"/>'
            f'<radialGradient id="blift" cx="50%" cy="50%" r="55%"><stop offset="0" stop-color="#171717"/><stop offset="1" stop-color="{BG}"/></radialGradient>'
            f'<rect width="{W}" height="{H}" fill="url(#blift)"/>' + _traces(W, H, (sx0, sy0, sx0 + 1546, sy0 + 423))
            + f'<ellipse cx="{x0 + mpx * .89:.0f}" cy="{cy + mpx * .24:.0f}" rx="420" ry="260" fill="url(#halo)"/>'
            + lock + f'<path d="{tag}" fill="{G3}"/>' + grain(W, H, .035))
    return svg(W, H, body, defs(5.5))

def banner_preview(png, out):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(png).convert("RGB"); d = ImageDraw.Draw(im, "RGBA"); f = ImageFont.truetype(FD + "Inter-Medium.otf", 30)
    W, H = im.size
    for (w, h, col, name) in ((2560, 423, (255, 200, 0), "desktop 2560x423"), (1855, 423, (0, 200, 255), "tablet 1855x423"),
                              (1546, 423, (255, 60, 60), "SAFE (mobile) 1546x423")):
        x0, y0 = (W - w) / 2, (H - h) / 2; d.rectangle((x0, y0, x0 + w - 1, y0 + h - 1), outline=col + (255,), width=4)
        d.text((x0 + 12, y0 + 8 if name.startswith("SAFE") else y0 - 40), name, font=f, fill=col + (255,))
    d.text((20, 20), "TV: full 2560x1440", font=f, fill=(200, 200, 200, 255)); im.save(out, quality=90)

def watermark():
    """150x150 transparent: the mark alone, with a soft shadow so it reads on bright footage too."""
    s = 150; m = 116
    sh = ('<filter id="sh" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="1.5" stdDeviation="3" '
          'flood-color="#000" flood-opacity=".55"/></filter>')
    body = f'<g filter="url(#sh)">' + place(mark_B(INK, FILAMENT, 9.2, .6), (s - m) / 2 - 3, (s - m) / 2 - 3, m) + "</g>"
    return svg(s, s, body, defs(3.2).replace("</defs>", sh + "</defs>"))

def final():
    out = HERE; L = os.path.join(out, "logo"); os.makedirs(L, exist_ok=True); jobs = []
    # mark: brand colours (with glow), and flat one-colour versions for any background
    marks = {"quietcircuit-mark": mark_B(INK, FILAMENT, **OPT),
             "quietcircuit-mark-white": mark_B("#FFFFFF", "#FFFFFF", 8.6, 0),
             "quietcircuit-mark-black": mark_B(BG, BG, 8.6, 0)}
    for k, m in marks.items():
        sv = svg(1024, 1024, place(m, 112, 112, 800), defs(3.2)); write(os.path.join(L, k + ".svg"), sv)
        jobs.append({"svg": sv, "out": os.path.join(L, k + ".png"), "w": 1024, "h": 1024})
    # lockups: dark (primary), light, transparent
    for name, bg, ink, quiet, light in (("quietcircuit-logo-dark", BG, INK, G4, FILAMENT), ("quietcircuit-logo-light", "#F5F5F2", BG, G3, "#0A0A0A"),
                                         ("quietcircuit-logo-transparent", None, INK, G4, FILAMENT)):
        lk, w = lockup(mark_B, "weights", 200, 0, 0, ink, light, quiet, glow=.85 if bg != "#F5F5F2" else 0, sw=8.6)
        Wd, Hd = int(w + 240), 440
        body = (f'<rect width="{Wd}" height="{Hd}" fill="{bg}"/>' if bg else "") + f'<g transform="translate(120 {Hd / 2})">{lk}</g>'
        sv = svg(Wd, Hd, body, defs(4.5)); write(os.path.join(L, name + ".svg"), sv)
        jobs.append({"svg": sv, "out": os.path.join(L, name + ".png"), "w": Wd, "h": Hd})
    # small-use wordmark (caps) for in-video / UI
    wm, w = wordmark("caps", 60, 0, 0); Wd = int(w + 80)
    sv = svg(Wd, 120, f'<g transform="translate(40 {60 + cap_height("Medium", 60) / 2})">{wm}</g>'); write(os.path.join(L, "quietcircuit-wordmark-caps.svg"), sv)
    jobs.append({"svg": sv, "out": os.path.join(L, "quietcircuit-wordmark-caps.png"), "w": Wd, "h": 120})
    # profile picture, banner, watermark
    pf = avatar(mark_B, FILAMENT, 800, .62, 8.6, .85, (-.025, -.02)); write(os.path.join(out, "profile_800.svg"), pf)
    jobs.append({"svg": pf, "out": os.path.join(out, "profile_800.png"), "w": 800, "h": 800})
    bn = banner(); write(os.path.join(out, "banner_2560x1440.svg"), bn)
    jobs.append({"svg": bn, "out": os.path.join(out, "banner_2560x1440.png"), "w": 2560, "h": 1440})
    wmk = watermark(); write(os.path.join(out, "watermark_150.svg"), wmk)
    jobs.append({"svg": wmk, "out": os.path.join(out, "watermark_150.png"), "w": 150, "h": 150})
    rasterize(jobs)
    banner_preview(os.path.join(out, "banner_2560x1440.png"), os.path.join(out, "options", "banner_safe_preview.jpg"))
    from PIL import Image                     # YouTube wants JPG/PNG < 6 MB for the banner; keep a JPG too
    Image.open(os.path.join(out, "banner_2560x1440.png")).convert("RGB").save(os.path.join(out, "banner_2560x1440.jpg"), quality=95)
    print("final ->", out)

if __name__ == "__main__":
    {"explore": explore, "final": final}[sys.argv[1] if len(sys.argv) > 1 else "explore"]()
