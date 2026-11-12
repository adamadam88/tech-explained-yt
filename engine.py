"""Premium vertical Shorts engine (1080x1920 @ 60 fps) for Quiet Circuit (@quietcircuit). Design rules: STYLE.md.

Monochrome base (#0A0A0A / #F5F5F2 / greys) + ONE accent per category, Inter Display with tight tracking,
fade + blur-to-focus + small drift entrances with ease-out-expo (no bounce, no shake), frosted-glass panels,
soft shadows, blurred bokeh depth layer, subtle vignette and film grain, slow constant camera.
3D hero objects (Three.js, studio3d.cjs) and Lucide icons arrive as pre-rendered PNGs.

Templates are `fn(arr, t, data, ctx)` drawing into a numpy RGB frame; EVENTS[name](data, ctx) -> [(t, sfx)].
"""
import math, os, re
from functools import lru_cache
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 60
SAFE_T, SAFE_B, SAFE_R, SAFE_L = 250, 420, 140, 60          # YouTube UI no-go zones
X0, X1 = SAFE_L, W - SAFE_R                                 # 60 .. 940
CX = (X0 + X1) // 2                                         # 500: content centre (left of the buttons)
MAXW = 800                                                  # visual text width (camera adds ~3 %)
CAP_W, CAP_Y = 800, 1345                                    # captions (drawn after the camera)
OUT_CX, FIT = W // 2, .96            # final frame: content (designed around CX) is centred on 540 and fitted to 96 %
ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(ROOT, "assets", "icons")
FD = "/usr/share/fonts/opentype/inter/"

def hexrgb(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
BG, INK = hexrgb("0A0A0A"), hexrgb("F5F5F2")
G1, G2, G3, G4 = hexrgb("161616"), hexrgb("2C2C2C"), hexrgb("77776F"), hexrgb("A9A9A3")
ACCENTS = {"ai": "#8B7CFF", "hardware": "#FFB547", "internet": "#4DA3FF", "space": "#5CE1E6",
           "security": "#FF5A5A", "mobile": "#7CFFB2", "energy": "#D4FF3A"}
CATEGORY_HINTS = {
    "ai": ["ai", "chatgpt", "neural", "machine learning", "llm", "robot"],
    "hardware": ["chip", "cpu", "gpu", "transistor", "semiconductor", "taiwan", "hardware", "microwave"],
    "internet": ["internet", "wi-fi", "wifi", "cloud", "website", "network", "cable", "whatsapp", "qr"],
    "space": ["gps", "satellite", "space", "orbit", "rocket", "starlink", "moon"],
    "security": ["password", "hack", "security", "robot?", "captcha", "scam", "encryption"],
    "mobile": ["phone", "app", "touchscreen", "face id", "shazam", "airplane mode", "headphones"],
    "energy": ["battery", "charging", "charger", "solar", "electric", "ev "],
}
def guess_category(topic):
    t = " " + topic.lower() + " "
    best = max(CATEGORY_HINTS, key=lambda c: sum(k in t for k in CATEGORY_HINTS[c]))
    return best if any(k in t for k in CATEGORY_HINTS[best]) else "internet"

@lru_cache(None)
def F(weight, size):
    size = max(8, int(size))
    return ImageFont.truetype(FD + (f"InterDisplay-{weight}.otf" if size >= 40 else f"Inter-{weight}.otf"), size)

# ---------------------------------------------------------------- easing (no overshoot anywhere)
def clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def expo(x): x = clamp(x); return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)
def smooth(x): x = clamp(x); return x * x * (3 - 2 * x)
def enter(t, t0, dur=.75, dist=30.0, blur=14.0):
    """fade + blur-to-focus + small upward drift. -> (alpha, blur_sigma, dy)"""
    if t0 is None or t < t0: return 0.0, blur, dist
    p = expo((t - t0) / dur)
    return smooth((t - t0) / (dur * .55)), blur * (1 - p), dist * (1 - p)
def mixc(a, b, k): return tuple(int(a[i] + (b[i] - a[i]) * clamp(k)) for i in range(3))

# ---------------------------------------------------------------- text sprites (tracking, blur, cached)
CAP = 0.727                                                  # Inter cap height (em)
def tokens(s):
    """'a *b c* d' -> [('a',False),('b',True),('c',True),('d',False)]"""
    out, on = [], False
    for w in s.split():
        st = w.startswith("*")
        en = bool(re.search(r"\*[^*\w]*$", w)) and not (st and w.count("*") == 1)
        if st: on = True
        out.append((w.replace("*", ""), on))
        if en: on = False
    return out

@lru_cache(4096)
def _sprite(s, weight, size, track):
    f = F(weight, size); asc, desc = f.getmetrics(); pad = int(size * .25) + 30; tr = track * size
    wid = (f.getlength(s) + tr * (len(s) - 1)) if s else 0.0
    im = Image.new("L", (int(math.ceil(wid)) + 2 * pad, asc + desc + 2 * pad), 0); d = ImageDraw.Draw(im)
    if abs(tr) < .01: d.text((pad, pad + asc), s, font=f, fill=255, anchor="ls")
    else:
        for i, ch in enumerate(s): d.text((pad + f.getlength(s[:i]) + i * tr, pad + asc), ch, font=f, fill=255, anchor="ls")
    return np.asarray(im, np.float32) / 255.0, pad, pad + asc, wid

@lru_cache(4096)
def _sprite_blur(s, weight, size, track, sigma):
    m, p, b, w = _sprite(s, weight, size, track)
    return cv2.GaussianBlur(m, (0, 0), sigma), p, b, w

def tw(s, weight, size, track=0.0): return _sprite(s, weight, int(size), round(track, 3))[3]

def fit(s, weight, maxsize, maxw, track=0.0, minsize=28):
    size = int(maxsize)
    while size > minsize and tw(s, weight, size, track) > maxw: size -= 4
    return size

def comp(arr, m, ox, oy, color, alpha=1.0):
    """Alpha-composite a float mask in a solid colour."""
    if alpha <= 0.004: return
    h, w = m.shape; ox, oy = int(round(ox)), int(round(oy))
    x0, y0, x1, y1 = max(0, ox), max(0, oy), min(arr.shape[1], ox + w), min(arr.shape[0], oy + h)
    if x1 <= x0 or y1 <= y0: return
    mm = m[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    if alpha < 1: mm = mm * alpha
    roi = arr[y0:y1, x0:x1]; r = roi.astype(np.float32)
    r += (np.array(color, np.float32) - r) * mm[..., None]
    roi[:] = (r + .5).astype(np.uint8)

def text(arr, s, x, y, weight="SemiBold", size=60, color=INK, alpha=1.0, ax="m", ay="c", track=0.0, blur=0.0, shadow=0.0):
    """ay='c' centres on the cap height (optical centre), ay='b' puts the baseline at y."""
    if not s or alpha <= 0.004: return 0
    size, track = int(size), round(track, 3); bq = round(blur * 2) / 2
    m, pad, base, wid = _sprite(s, weight, size, track) if bq < .5 else _sprite_blur(s, weight, size, track, bq)
    ox = x - pad - {"l": 0, "m": wid / 2, "r": wid}[ax]; oy = y - base + (CAP * size / 2 if ay == "c" else 0)
    if shadow:
        sm = _sprite_blur(s, weight, size, track, max(6.0, size * .1))[0]
        comp(arr, sm, ox, oy + size * .05, (0, 0, 0), shadow * alpha)
    comp(arr, m, ox, oy, color, alpha)
    return wid

def text_tnum(arr, s, x, y, weight, size, color, alpha=1.0, ax="l"):
    """Tabular figures (digits in fixed cells) so ticking numbers don't jitter."""
    cell = tw("0", weight, size); widths = [cell if c.isdigit() else tw(c, weight, size) for c in s]
    xx = x - {"l": 0, "m": sum(widths) / 2, "r": sum(widths)}[ax]
    for c, w in zip(s, widths):
        text(arr, c, xx + w / 2, y, weight, size, color, alpha, "m"); xx += w

def words_line(arr, toks, x, y, weight, size, track, color, kcolor, states=None, ax="m", shadow=0.0):
    sp = tw(" ", weight, size) + track * size
    ws = [tw(w, weight, size, track) for w, _ in toks]; total = sum(ws) + sp * (len(ws) - 1)
    xx = x - total / 2 if ax == "m" else x
    for i, ((w, k), ww) in enumerate(zip(toks, ws)):
        a, b, dy = states[i] if states else (1.0, 0.0, 0.0)
        text(arr, w, xx, y + dy, weight, size, kcolor if k else color, a, "l", "c", track, b, shadow)
        xx += ww + sp
    return total

def label(arr, s, x, y, color=G3, alpha=1.0, size=27, ax="m", blur=0.0):
    """Small, thin, widely tracked uppercase secondary text."""
    return text(arr, s.upper(), x, y, "Medium", size, color, alpha, ax, "c", .2, blur)

# ---------------------------------------------------------------- shapes, glass, icons, 3D layers
@lru_cache(256)
def rr_mask(w, h, r, inset=0.0, ss=4):
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).rounded_rectangle((inset * ss, inset * ss, (w - inset) * ss - 1, (h - inset) * ss - 1), max(1, (r - inset) * ss), fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0

@lru_cache(256)
def rr_border(w, h, r, th=1.5): return np.clip(rr_mask(w, h, r) - rr_mask(w, h, r, th), 0, 1)

@lru_cache(128)
def rr_shadow(w, h, r, sig=30):
    pad = int(sig * 3); m = np.zeros((h + 2 * pad, w + 2 * pad), np.float32)
    m[pad:pad + h, pad:pad + w] = rr_mask(w, h, r); return cv2.GaussianBlur(m, (0, 0), sig), pad

@lru_cache(64)
def disc(r, sigma=0.0):
    pad = int(r + sigma * 3 + 4); ss = 4
    im = Image.new("L", (2 * pad * ss, 2 * pad * ss), 0)
    ImageDraw.Draw(im).ellipse(((pad - r) * ss, (pad - r) * ss, (pad + r) * ss, (pad + r) * ss), fill=255)
    m = np.asarray(im.resize((2 * pad, 2 * pad), Image.LANCZOS), np.float32) / 255.0
    return (cv2.GaussianBlur(m, (0, 0), sigma) if sigma else m), pad

def dot(arr, x, y, r, color, alpha=1.0, glow=0.0):
    if glow: m, p = disc(int(r * 2.5), r * 1.6); comp(arr, m, x - p, y - p, color, alpha * glow)
    m, p = disc(int(r)); comp(arr, m, x - p, y - p, color, alpha)

@lru_cache(16)
def _vgrad(h): return (np.linspace(1, 0, h, dtype=np.float32) ** 2.5 * 12)[:, None, None]

def glass(arr, box, r=40, alpha=1.0, tint=.05, border=.16, blur=28, shadow=.55):
    """Frosted glass: blurred backdrop + light tint + top sheen + hairline border + soft drop shadow."""
    if alpha <= 0.004: return
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(W, x1), min(H, y1); w, h = x1 - x0, y1 - y0
    if w < 8 or h < 8: return
    sm, pad = rr_shadow(w, h, r); comp(arr, sm, x0 - pad, y0 - pad + 26, (0, 0, 0), shadow * alpha)
    roi = arr[y0:y1, x0:x1]
    small = cv2.resize(roi, (max(2, w // 4), max(2, h // 4)), interpolation=cv2.INTER_AREA)
    bl = cv2.resize(cv2.GaussianBlur(small, (0, 0), blur / 4), (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    gl = bl * (1 - tint) + 255 * tint + _vgrad(h)
    m = rr_mask(w, h, r)[..., None] * alpha
    roi[:] = (roi * (1 - m) + gl * m + .5).astype(np.uint8)
    comp(arr, rr_border(w, h, r), x0, y0, INK, border * alpha)

ICON_REQ = set()
ICON_STROKE = 3.0                       # uniform absolute stroke (px) for every Lucide icon
@lru_cache(256)
def icon_mask(name, size):
    p = os.path.join(ICON_DIR, f"{name}_{size}.png")
    if not os.path.exists(p): ICON_REQ.add((name, size)); return None
    return cv2.imread(p, cv2.IMREAD_UNCHANGED)[..., 3].astype(np.float32) / 255.0

def icon(arr, name, x, y, size, color=G4, alpha=1.0, blur=0.0):
    m = icon_mask(name, int(size))
    if m is None or alpha <= 0.004: return
    if blur > .5: m = cv2.GaussianBlur(m, (0, 0), blur)
    comp(arr, m, x - size / 2, y - size / 2, color, alpha)

_OBJ = {}
def obj_frame(d, fi):
    key = (d, fi)
    if key not in _OBJ:
        if len(_OBJ) > 8: _OBJ.clear()
        im = cv2.imread(os.path.join(d, f"{fi:05d}.png"), cv2.IMREAD_UNCHANGED)
        _OBJ[key] = None if im is None else im[..., [2, 1, 0, 3]]
    return _OBJ[key]

def layer(arr, rgba, cx, cy, alpha=1.0, blur=0.0):
    if rgba is None or alpha <= 0.004: return
    if blur > .5: rgba = cv2.GaussianBlur(rgba, (0, 0), blur)
    h, w = rgba.shape[:2]; ox, oy = int(round(cx - w / 2)), int(round(cy - h / 2))
    x0, y0, x1, y1 = max(0, ox), max(0, oy), min(W, ox + w), min(H, oy + h)
    if x1 <= x0 or y1 <= y0: return
    src = rgba[y0 - oy:y1 - oy, x0 - ox:x1 - ox].astype(np.float32)
    a = src[..., 3:4] / 255.0 * alpha; roi = arr[y0:y1, x0:x1]
    roi[:] = (roi * (1 - a) + src[..., :3] * a + .5).astype(np.uint8)

# ---------------------------------------------------------------- background: depth, glow, bokeh, vignette, grain
class Background:
    def __init__(self, accent, seed=0):
        self.accent = hexrgb(accent) if isinstance(accent, str) else accent
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); self.yy, self.xx = yy, xx
        lift = np.exp(-(((xx - CX) / 700) ** 2 + ((yy - 820) / 900) ** 2))[..., None]
        self.base = np.array(BG, np.float32) + 9 * lift                       # #0A0A0A lifting to ~#131313
        v = 1 - .38 * np.clip(((xx - W / 2) / (W * .78)) ** 2 + ((yy - H / 2) / (H * .7)) ** 2, 0, 1)
        self.vig = (v * 256).astype(np.uint16)[..., None]
        rng = np.random.default_rng(seed)
        # fine static dither (±1 level): kills gradient banding without feeding YouTube's encoder moving noise
        self.grain = [np.round(rng.random((H, W, 1)) - rng.random((H, W, 1))).astype(np.int16)]
        self.bokeh = [(rng.uniform(40, W - 40), rng.uniform(300, H - 300), int(rng.uniform(50, 150)), rng.uniform(-6, 6), rng.uniform(-10, -3),
                       rng.uniform(.025, .055), self.accent if k < 2 else G4) for k in range(7)]
        self._glow = {}

    def _with_glow(self, gx, gy, s):
        key = (int(gx), int(gy), round(s, 1))
        if key not in self._glow:
            if len(self._glow) > 6: self._glow.clear()
            g = np.exp(-(((self.xx - gx) / 430) ** 2 + ((self.yy - gy) / 470) ** 2))[..., None] * .085 * s
            self._glow[key] = np.clip(self.base * (1 - g) + np.array(self.accent, np.float32) * g, 0, 255).astype(np.uint8)
        return self._glow[key]

    def frame(self, T, glow=(CX, 800), strength=1.0):
        arr = self._with_glow(glow[0], glow[1], strength).copy()
        for x, y, r, vx, vy, a, c in self.bokeh:
            m, p = disc(r, r * .35)
            comp(arr, m, (x + vx * T) % W - p, (y + vy * T) % H - p, c, a)
        return arr

    def finish(self, arr, fi):
        out = (arr.astype(np.uint16) * self.vig >> 8).astype(np.int16) + self.grain[0]
        return np.clip(out, 0, 255).astype(np.uint8)

# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, accent, D, words, T0=0.0, index=0):
        self.accent = hexrgb(accent) if isinstance(accent, str) else accent
        self.D, self.words, self.T0, self.index = D, words, T0, index
    def at(self, spec, default=0.0):
        """int -> start of word #n, float<=1 -> fraction of beat, float>1 -> seconds, str -> first word containing it."""
        if spec is None or isinstance(spec, bool): return default
        if isinstance(spec, int):
            return self.words[min(spec, len(self.words) - 1)]["start"] if self.words else default
        if isinstance(spec, float): return spec * self.D if spec <= 1 else spec
        s = str(spec).lower()
        for w in self.words:
            if s in w["text"].lower(): return w["start"]
        return default
    def word_times(self, n):
        if not self.words: return [i * self.D / max(1, n) * .8 for i in range(n)]
        m = len(self.words); return [self.words[min(m - 1, int(i * m / n))]["start"] for i in range(n)]

def _lines(s): return [l.strip() for l in s.split("|")]

def headline(arr, t, ctx, s, y, maxsize=170, t0=0.0, sync=False, weight="SemiBold", track=-.035, lh=1.08):
    """Big centred statement; '|' breaks lines; *word* in accent; words enter staggered (or synced to voice)."""
    lines = [tokens(l) for l in _lines(s)]
    size = min(fit(" ".join(w for w, _ in tk), weight, maxsize, MAXW, track) for tk in lines)
    n = sum(len(tk) for tk in lines)
    times = ctx.word_times(n) if sync else [t0 + .07 * i for i in range(n)]
    yy = y - (len(lines) - 1) * size * lh / 2; k = 0
    for tk in lines:
        st = [enter(t, times[k + i] - .03, .8, 26, 16) for i in range(len(tk))]; k += len(tk)
        words_line(arr, tk, CX, yy, weight, size, track, INK, ctx.accent, st)
        yy += size * lh
    return size

# ---------------------------------------------------------------- templates
def t_hook(arr, t, d, ctx):
    shots = d["shots"]; times = [ctx.at(s.get("at"), 0.0) for s in shots]
    cur = max([i for i, ts in enumerate(times) if t >= ts - 1e-6] or [0])
    y = d.get("y", 560)
    for i, s in enumerate(shots):
        if i > cur: continue
        fade_out = 1.0
        if i < cur:
            fade_out = 1 - smooth((t - times[cur]) / .16)
            if fade_out <= 0: continue
        ts = times[i] if i else -1.0          # the very first shot is already on screen at frame 0
        size = fit(" ".join(w for w, _ in tokens(s["big"].replace("|", " "))), "SemiBold", d.get("size", 168), MAXW, -.035)
        if s.get("small"):
            a, b, dy = enter(t, ts, .7, 16, 10)
            label(arr, s["small"], CX, y - size * .55 - 58 + dy, G4, a * fade_out, 30, blur=b)
        tk = tokens(s["big"]); st = []
        for j in range(len(tk)):
            a, b, dy = enter(t, ts + .06 * j, .8, 26, 16); st.append((a * fade_out, b + 10 * (1 - fade_out), dy))
        words_line(arr, tk, CX, y, "SemiBold", size, -.035, INK, ctx.accent, st)

def t_number(arr, t, d, ctx):
    t0 = ctx.at(d.get("at"), .03); dur = d.get("dur", 1.1)
    if d.get("icon"):
        a, b, dy = enter(t, t0, .8, 20, 10); icon(arr, d["icon"], CX, d.get("icon_y", 520) + dy, 128, G4, a, b)
    p = expo((t - t0) / dur); v = d.get("from", 0) + (d["value"] - d.get("from", 0)) * p; dec = d.get("decimals", 0)
    final = f"{d.get('prefix', '')}{d['value']:,.{dec}f}"; s = f"{d.get('prefix', '')}{v:,.{dec}f}"
    unit = d.get("unit", ""); size = fit(final + unit, "SemiBold", d.get("size", 300), MAXW - 40, -.045)
    us = size * .3; uw = tw(unit, "Medium", us) + 20 if unit else 0
    nw = tw(final, "SemiBold", size, -.045); x = CX - (nw + uw) / 2; y = d.get("y", 800)
    a, b, dy = enter(t, t0 - .05, .9, 30, 18)
    text(arr, s, x, y + dy, "SemiBold", size, INK, a, "l", "c", -.045, b)
    if unit: text(arr, unit, x + nw + 20, y + size * CAP / 2 + dy, "Medium", us, G4, a, "l", "b", -.01, b)
    la, lb, ldy = enter(t, ctx.at(d.get("label_at"), t0 + .35), .8, 14, 8)
    hw = 70 * expo((t - t0 - .3) / .9)
    if hw > 1: comp(arr, np.ones((3, int(hw * 2)), np.float32), CX - hw, y + size * .48 + 22, ctx.accent, la)
    if d.get("label"): label(arr, d["label"], CX, y + size * .48 + 80 + ldy, G4, la, 30, blur=lb)
    if d.get("sub"):
        sa, sb, sdy = enter(t, ctx.at(d.get("sub_at"), t0 + .7), .8, 12, 8)
        text(arr, d["sub"], CX, y + size * .48 + 140 + sdy, "Regular", 34, G3, sa, "m", "c", 0, sb)

def t_versus(arr, t, d, ctx):
    for key, box, at_key, dflt in (("a", (90, 390, 910, 700), "a_at", .02), ("b", (90, 800, 910, 1110), "b_at", .4)):
        P = d[key]; t0 = ctx.at(d.get(at_key), dflt); a, b, dy = enter(t, t0, .8, 40, 0)
        if a <= 0: continue
        x0, y0, x1, y1 = box; y0 += dy; y1 += dy; important = key == "b"
        glass(arr, (x0, y0, x1, y1), 44, a)
        label(arr, P["label"], x0 + 56, y0 + 76, G3, a, 26, "l")
        vs = fit(P["value"], "SemiBold", 128, 560, -.035)
        _, tb, tdy = enter(t, t0 + .12, .8, 16, 12)
        text(arr, P["value"], x0 + 52, y0 + 200 + tdy, "SemiBold", vs, ctx.accent if important else INK, a, "l", "c", -.035, tb)
        if P.get("icon"): icon(arr, P["icon"], x1 - 110, (y0 + y1) / 2, 112, ctx.accent if important else G4, a * .9, tb)
    a, _, _ = enter(t, ctx.at(d.get("b_at"), .4) - .1, .6)
    label(arr, "vs", CX, 750, G3, a, 26)

def t_globe(arr, t, d, ctx):
    t0 = ctx.at(d.get("at"), .05); dur = d.get("dur", 1.6); n = d.get("count", 24)
    shown = int(round(n * expo((t - t0) / dur) if t > t0 else 0))
    a, b, dy = enter(t, t0 - .1, .8, 20, 12)
    s = f"{d.get('prefix', '')}{shown:,}{d.get('suffix', '') if shown == n else ''}"
    if d.get("counter", True): text_tnum(arr, s, CX, 490 + dy, "SemiBold", 140, INK, a, "m")
    ts = ctx.at(d.get("sub_at"), 99.0); k = smooth((t - ts) / .3)
    if d.get("label"): label(arr, d["label"], CX, 385 + dy, G4, a * (1 - k), 28, blur=b + 10 * k)
    if d.get("sub"):
        sa, sb, sdy = enter(t, ts + .1, .7, 12, 10); label(arr, d["sub"], CX, 385 + sdy, ctx.accent, sa, 28, blur=sb)

def _dashed(arr, p0, p1, color, alpha=1.0, dash=10, gap=12, th=2):
    L = math.dist(p0, p1); n = int(L / (dash + gap)); ov = arr.copy() if alpha < 1 else arr
    for i in range(n):
        a0 = i * (dash + gap) / L; a1 = (i * (dash + gap) + dash) / L
        q0 = (int(p0[0] + (p1[0] - p0[0]) * a0), int(p0[1] + (p1[1] - p0[1]) * a0))
        q1 = (int(p0[0] + (p1[0] - p0[0]) * a1), int(p0[1] + (p1[1] - p0[1]) * a1))
        cv2.line(ov, q0, q1, color, th, cv2.LINE_AA)
    if alpha < 1: cv2.addWeighted(ov, alpha, arr, 1 - alpha, 0, dst=arr)

def t_signal(arr, t, d, ctx):
    p0, p1 = (470, 650), (735, 840)
    a, _, _ = enter(t, .25, .6)
    if a > 0:
        _dashed(arr, p0, p1, G3, a)
        for k in range(2):
            q = ((t * .55 + k * .5) % 1.0)
            dot(arr, p0[0] + (p1[0] - p0[0]) * q, p0[1] + (p1[1] - p0[1]) * q, 6, ctx.accent, a * smooth(q * 6) * smooth((1 - q) * 6), glow=.5)
    rows = d.get("rows", []); ats = d.get("row_at", [])
    if rows:
        t0 = ctx.at(ats[0] if ats else None, .15); ga, _, gdy = enter(t, t0 - .1, .8, 30, 0)
        box = (90, 930 + gdy, 600, 930 + 70 + 120 * len(rows) + gdy); glass(arr, box, 36, ga)
        ms = int((ctx.T0 + t) * 1000) % 1000
        for i, (lab, val) in enumerate(rows):
            ti = ctx.at(ats[i] if i < len(ats) else None, .2 + .35 * i); ra, rb, rdy = enter(t, ti, .7, 14, 10)
            y = box[1] + 70 + 120 * i
            label(arr, lab, box[0] + 46, y - 6 + rdy, G3, ra * ga, 24, "l", rb)
            v = val.replace("{ms}", f"{ms:03d}")
            text_tnum(arr, v, box[0] + 44, y + 48 + rdy, "Medium", 50, ctx.accent if "{ms}" in val else INK, ra * ga, "l")

def t_flow(arr, t, d, ctx):
    nodes = d["nodes"]; n = len(nodes); ys = [470 + i * 230 for i in range(n)]
    ats = d.get("at", []); times = [ctx.at(ats[i] if i < len(ats) else None, .05 + i * .3) for i in range(n)]
    for i in range(1, n):
        k = expo((t - times[i] + .25) / .5)
        if k > 0:
            ya, yb = ys[i - 1] + 68, ys[i] - 68
            cv2.line(arr, (CX, int(ya)), (CX, int(ya + (yb - ya) * k)), G2, 2, cv2.LINE_AA)
    for i, nd in enumerate(nodes):
        a, b, dy = enter(t, times[i], .8, 30, 12)
        if a <= 0: continue
        active = i == n - 1 or t < times[i + 1]
        dim = 1.0 if active else .42; last = i == n - 1
        y = ys[i] + dy; glass(arr, (90, y - 68, 910, y + 68), 68, a * (1 if active else .7))
        if nd.get("icon"): icon(arr, nd["icon"], 175, y, 64, ctx.accent if active else G4, a * dim, b)
        text(arr, nd["text"], 240, y, "Medium", 58, ctx.accent if (last and active) else INK, a * dim, "l", "c", -.02, b)

RING_SATS = [(240, 570), (790, 600), (480, 1210)]
def t_rings(arr, t, d, ctx):
    tgt = (CX, 860); show, start = d.get("show", 3), d.get("start", 0); ats = d.get("at", [])
    ov = arr.copy()
    for i in range(show):
        c = RING_SATS[i]; r = int(math.dist(c, tgt))
        k = 1.0 if i < start else expo((t - ctx.at(ats[i] if i < len(ats) else None, .05 + (i - start) * .3)) / 1.1)
        if k <= 0: continue
        cv2.ellipse(ov, c, (r, r), -90 + 35 * i, 0, 360 * k, G4 if show > 1 else ctx.accent, 2, cv2.LINE_AA)
    cv2.addWeighted(ov, .85, arr, .15, 0, dst=arr)
    for i in range(show):
        k = 1.0 if i < start else enter(t, ctx.at(ats[i] if i < len(ats) else None, .05 + (i - start) * .3), .7, 14, 10)[0]
        icon(arr, "satellite", RING_SATS[i][0], RING_SATS[i][1], 64, INK, k)
    if show == 1:
        c = RING_SATS[0]; r = math.dist(c, tgt); a, _, _ = enter(t, .4, .8)
        for k in range(3):
            ang = .9 + t * .35 + k * 2.1
            dot(arr, c[0] + r * math.cos(ang), c[1] + r * math.sin(ang), 7, INK, a * .9, glow=.35)
        if d.get("label"):
            la, lb, ldy = enter(t, .1, .8, 12, 8); label(arr, d["label"], CX, 1150 + ldy, G4, la, 28, blur=lb)
    else:
        ty = ctx.at(d.get("you_at"), .7); a, b, dy = enter(t, ty, .8, 0, 10)
        if a > 0:
            pulse = 1 + .08 * math.sin((t - ty) * 3)
            dot(arr, tgt[0], tgt[1], 11 * pulse, ctx.accent, a, glow=.7)
            text(arr, d.get("you", "You"), tgt[0], tgt[1] - 70, "SemiBold", 64, INK, a, "m", "c", -.02, b, shadow=.6)

def t_list(arr, t, d, ctx):
    a, b, dy = enter(t, 0, .7, 14, 10)
    items, ats = d["items"], d.get("at", [])
    top = 800 - (len(items) * 190 + 170) / 2
    label(arr, d.get("title", ""), CX, top + dy, G4, a, 30, blur=b)
    hw = 60 * expo(t / .9); comp(arr, np.ones((2, max(1, int(hw * 2))), np.float32), CX - hw, top + 40, ctx.accent, a)
    for i, it in enumerate(items):
        ti = ctx.at(ats[i] if i < len(ats) else None, .15 + i * .3); ia, ib, idy = enter(t, ti, .8, 30, 12)
        if ia <= 0: continue
        y = top + 190 + i * 190 + idy; glass(arr, (90, y - 76, 910, y + 76), 40, ia)
        if it.get("icon"): icon(arr, it["icon"], 160, y, 64, ctx.accent if it.get("key", True) else G4, ia, ib)
        else: text(arr, it["n"], 160, y, "SemiBold", 66, ctx.accent, ia, "m", "c", -.03, ib)
        text(arr, it["text"], 240, y, "Medium", fit(it["text"], "Medium", 50, 620, -.015), INK, ia, "l", "c", -.015, ib)
    if d.get("icon"):
        a2, b2, dy2 = enter(t, ctx.at(d.get("icon_at"), .5), .8, 20, 12)
        icon(arr, d["icon"], CX, 1150 + dy2, 112, G4, a2, b2)

def t_insight(arr, t, d, ctx):
    a, b, dy = enter(t, 0, .7, 12, 8)
    k = d.get("kicker", "Did you know"); kw = tw(k.upper(), "Medium", 27, .2)
    label(arr, k, CX, 420 + dy, ctx.accent, a, 27, blur=b)
    for s in (-1, 1): comp(arr, np.ones((2, 40), np.float32), CX + s * (kw / 2 + 24) - (40 if s < 0 else 0), 420, ctx.accent, a * .8)
    if d.get("icon"):
        ia, ib, idy = enter(t, .12, .8, 20, 12); icon(arr, d["icon"], CX, 610 + idy, 144, G4, ia, ib)
    headline(arr, t, ctx, d["text"], 850, d.get("size", 150), t0=.25)
    if d.get("small"):
        sa, sb, sdy = enter(t, ctx.at(d.get("small_at"), .55), .8, 12, 8); label(arr, d["small"], CX, 1030 + sdy, G4, sa, 30, blur=sb)

def t_chart(arr, t, d, ctx):
    a, b, dy = enter(t, 0, .7, 12, 8); label(arr, d.get("title", ""), CX, 400 + dy, G4, a, 28, blur=b)
    bars = d["bars"]; n = len(bars); vmax = max(v for _, v in bars) * 1.08
    bx0, bx1, base, top = 130, 870, 1130, 540
    cv2.line(arr, (bx0 - 10, base), (bx1 + 10, base), G2, 2, cv2.LINE_AA)
    slot = (bx1 - bx0) / n; bw = int(slot * .5); ats, unit = d.get("at", []), d.get("unit", "")
    for i, (lab, v) in enumerate(bars):
        ti = ctx.at(ats[i] if i < len(ats) else None, .1 + i * .7 / n); p = expo((t - ti) / 1.0)
        if p <= 0: continue
        x = int(bx0 + slot * i + (slot - bw) / 2); hh = int((base - top) * v / vmax * p)
        if hh > 2:
            m = rr_mask(bw, hh + 12, 12)[:hh]; comp(arr, m, x, base - hh, ctx.accent if i == n - 1 else G2, 1)
        s = f"{v * p:,.0f}{unit}"; la = smooth(p * 3)
        text(arr, s, x + bw / 2, base - hh - 40, "Medium", 40, INK if i == n - 1 else G4, la, "m", "c", -.01)
        label(arr, lab, x + bw / 2, base + 46, G3, la, 22)

def t_reveal(arr, t, d, ctx):
    if d.get("small"):
        a, b, dy = enter(t, 0, .7, 12, 8); label(arr, d["small"], CX, d.get("y", 760) - 190 + dy, G4, a, 30, blur=b)
    headline(arr, t, ctx, d["text"], d.get("y", 760), d.get("size", 190), sync=True)

def t_cell(arr, t, d, ctx):
    """Inside a lithium-ion cell: ions shuttle graphite <-> cathode; mode 'trap' grows the SEI crust that keeps some."""
    a, _, dy = enter(t, 0, .7, 30, 0)
    if a <= 0: return
    x0, y0, x1, y1 = 90, 400 + dy, 910, 1110 + dy; glass(arr, (x0, y0, x1, y1), 44, a)
    ax0, ax1, cx0, cx1 = x0 + 60, x0 + 300, x1 - 300, x1 - 60; top, bot = int(y0 + 150), int(y1 - 70)
    label(arr, "Graphite", (ax0 + ax1) / 2, y0 + 80, G4, a, 24); label(arr, "Cathode", (cx0 + cx1) / 2, y0 + 80, G4, a, 24)
    base = (30, 30, 30); line = mixc(base, (70, 70, 68), a)
    for y in range(top, bot + 1, 30): cv2.line(arr, (ax0, y), (ax1, y), line, 3, cv2.LINE_AA)       # graphite sheets
    for y in range(top + 8, bot - 8, 38):                                                               # layered oxide lattice
        for x in range(cx0 + 10, cx1 - 10, 38): cv2.rectangle(arr, (x, y), (x + 16, y + 16), line, -1, cv2.LINE_AA)
    _dashed(arr, (CX, top - 10), (CX, bot + 10), G3, a * .8, 8, 10, 2)
    trap = d.get("mode") == "trap"; tc = ctx.at(d.get("crust_at"), .08); g = expo((t - tc) / 2.2) if trap else 0.0
    cw = 46 * g
    if cw > 1:                                                                                          # SEI crust, rough edge
        ys = np.arange(top - 6, bot + 7, 6); xs = ax1 + 4 + cw * (.62 + .38 * np.sin(ys * .37) * np.cos(ys * .11))
        pts = np.concatenate([np.stack([xs, ys], 1), [[ax1 + 2, bot + 6], [ax1 + 2, top - 6]]]).astype(np.int32)
        cv2.fillPoly(arr, [pts], mixc(base, (112, 108, 96), a), cv2.LINE_AA)
        la, lb, ldy = enter(t, tc + .5, .7, 10, 8)
        label(arr, "SEI layer", ax1 + 26, bot + 46 + ldy, G4, la, 22, "l", lb)
    N = d.get("ions", 12); period = d.get("period", 2.6); trapped = 0
    for i in range(N):
        y = top + (i + .5) * (bot - top) / N + 6 * math.sin(i * 2.3)
        xa = ax0 + 30 + (i * 53) % (ax1 - ax0 - 60); xc = cx0 + 30 + (i * 71) % (cx1 - cx0 - 60)
        ph = (t / period + i * .37) % 1.0; k = smooth(min(1, ph * 2) if ph < .5 else max(0, 2 - ph * 2))
        x = xa + (xc - xa) * k; col, gl = ctx.accent, .6
        if trap and i % 3 == 1:
            tt = tc + .5 + trapped * .35; trapped += 1
            if t >= tt:
                x = ax1 + 4 + cw * .5; col, gl = G4, 0.0
                y = y
        dot(arr, x, y, 7, col, a, glow=gl)
    if trap and d.get("cycles"):
        n = int(1 + (d["cycles"] - 1) * expo((t - tc) / 2.6)); ca = enter(t, tc, .6)[0]
        nw = tw("0", "Medium", 36) * len(f"{d['cycles']:,}")
        text_tnum(arr, f"{n:,}", x1 - 56, y1 - 40, "Medium", 36, INK, ca * a, "r")
        label(arr, "Cycle", x1 - 56 - nw - 18, y1 - 40, G3, ca * a, 20, "r")

WALLS = {"drywall": (.85, "Drywall", "≈ −4 dB"), "brick": (.45, "Brick", "≈ −10 dB"),
         "concrete": (.2, "Concrete", "≈ −23 dB"), "metal": (0.0, "Metal", "Reflects")}
def t_wall(arr, t, d, ctx):
    """Wi-Fi wavefronts meeting a wall: drywall lets them through, concrete soaks them up, metal mirrors them back."""
    T, name, val = WALLS[d.get("material", "drywall")]; metal = d.get("material") == "metal"
    src, rcv = (175, 780), (825, 780); wx0, wx1 = (CX - 15, CX + 15) if metal else (CX - 38, CX + 38)
    a, b, dy = enter(t, 0, .7, 20, 8)
    Y0, Y1 = 400, 1170; M = np.zeros((Y1 - Y0, W), np.float32)
    for k in range(9):
        r = (t * 240 + k * 95) % 860
        if r < 30: continue
        f = (1 - r / 860) ** 1.2 * smooth(r / 120)
        cv2.ellipse(M, (src[0], src[1] - Y0), (int(r), int(r)), 0, -48, 48, f, 3, cv2.LINE_AA)
        if metal and r > wx0 - src[0]:                                            # mirror image source
            cv2.ellipse(M, (2 * wx0 - src[0], src[1] - Y0), (int(r), int(r)), 0, 132, 228, f * .85, 3, cv2.LINE_AA)
    M[:, wx1:] *= T; M[:, wx0:wx1] = 0
    if metal: M[:, wx0:] = 0
    comp(arr, M, 0, Y0, ctx.accent, a)
    hgt = 720; wy0 = 420
    if name == "Drywall": glass(arr, (wx0, wy0, wx1, wy0 + hgt), 10, a, tint=.09, border=.22)
    else:
        colr = {"Brick": (74, 66, 60), "Concrete": (62, 62, 60), "Metal": (160, 160, 156)}[name]
        comp(arr, rr_mask(wx1 - wx0, hgt, 8), wx0, wy0, colr, a)
        if metal: comp(arr, rr_mask(6, hgt - 20, 3), wx0 + 6, wy0 + 10, (230, 230, 226), a * .8)
        else:
            rng = np.random.default_rng(7)
            for _ in range(70): dot(arr, rng.uniform(wx0 + 8, wx1 - 8), rng.uniform(wy0 + 10, wy0 + hgt - 10), rng.uniform(1.5, 3.5), (46, 46, 44), a)
    label(arr, name, (wx0 + wx1) / 2, 380 + dy, G4, a, 26, blur=b)
    text(arr, val, (wx0 + wx1) / 2, 1200 + dy, "Medium", 36, ctx.accent if metal else INK, a, "m", "c", -.01, b)
    icon(arr, "router", src[0], src[1], 96, INK, a)
    icon(arr, "smartphone", rcv[0], rcv[1] + 20, 96, G4, a)
    icon(arr, "wifi", rcv[0], rcv[1] - 90, 64, ctx.accent if T > .5 else G3, a * (.25 + .75 * T))

def t_section(arr, t, d, ctx):
    """Cross-section of a subsea cable (glass fibres with light pulses / steel wires / copper tube / polyethylene)
    with a legend underneath; the layer being talked about is in the accent."""
    c = (CX, 700); hl = d.get("highlight", "fibers"); k = .8
    layers = [("fibers", 0.0, "Glass fibres"), ("steel", .25, "Steel wires · strength"), ("copper", .5, "Copper · power"), ("sheath", .75, "Polyethylene · insulation")]
    st = {key: enter(t, ctx.at(d.get(key + "_at"), dt), .8, 0, 0)[0] for key, dt, _ in layers}
    def col(key, base): return ctx.accent if key == hl else base
    bgc = (14, 14, 14)
    if st["sheath"] > 0:
        m, p = disc(int(330 * k)); comp(arr, m, c[0] - p, c[1] - p, (38, 38, 37), st["sheath"])
        m, p = disc(int(318 * k)); comp(arr, m, c[0] - p, c[1] - p, bgc, st["sheath"])
        cv2.circle(arr, c, int(330 * k), mixc(bgc, col("sheath", G3), st["sheath"]), 2, cv2.LINE_AA)
    if st["copper"] > 0:
        cv2.circle(arr, c, int(262 * k), mixc(bgc, col("copper", (150, 118, 92)), st["copper"]), 14, cv2.LINE_AA)
    if st["steel"] > 0:
        n = 22; rot = t * .15
        for i in range(n):
            ang = rot + i * 2 * math.pi / n; p = (c[0] + 205 * k * math.cos(ang), c[1] + 205 * k * math.sin(ang))
            m, pp = disc(20); comp(arr, m, p[0] - pp, p[1] - pp, col("steel", (120, 120, 116)), st["steel"])
            m, pp = disc(6); comp(arr, m, p[0] - pp - 6, p[1] - pp - 6, (210, 210, 206), st["steel"] * .35)
    if st["fibers"] > 0:
        cv2.circle(arr, c, int(130 * k), mixc(bgc, G3, st["fibers"]), 2, cv2.LINE_AA)
        for i in range(8):
            ang = i * 2 * math.pi / 8 + .3; r = (62 if i % 2 else 92) * k; p = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
            pulse = .55 + .45 * math.sin(t * 9 + i * 1.7)
            dot(arr, p[0], p[1], 8, col("fibers", INK), st["fibers"] * pulse, glow=.9 * pulse)
    for j, (key, _, txt) in enumerate(layers):                                   # legend
        la = st[key]
        if la <= 0: continue
        y = 1030 + j * 54; on = key == hl
        dot(arr, 250, y, 7, ctx.accent if on else G3, la)
        text(arr, txt, 280, y, "Medium", 34, INK if on else G4, la * (1 if on else .8), "l", "c", -.01)

def _face_h(x, y):
    """Relief of a stylised face on a unit ellipse (x, y in -1..1), 0..1: soft dome + strong features
    (nose ridge, deep eye sockets, brows, cheekbones, lips) so the dot cloud reads as a face."""
    g = lambda cx, cy, sx, sy: np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))
    dome = np.sqrt(np.clip(1 - x ** 2 - y ** 2, 0, 1))
    feat = (.75 * g(0, .02, .1, .34) + .35 * g(0, .3, .16, .07) - .7 * g(-.37, -.17, .17, .1) - .7 * g(.37, -.17, .17, .1)
            + .35 * g(-.37, -.33, .25, .05) + .35 * g(.37, -.33, .25, .05) + .25 * g(-.45, .15, .18, .14) + .25 * g(.45, .15, .18, .14)
            + .4 * g(0, .52, .22, .06) - .25 * g(0, .6, .2, .04))
    return np.clip(.25 * dome + .5 + .6 * feat, 0, 1)

@lru_cache(4)
def _face_grid(step=20):
    xs, ys = np.meshgrid(np.arange(-1, 1.0001, step / 230), np.arange(-1, 1.0001, step / 300))
    keep = xs ** 2 + ys ** 2 <= 1; x, y = xs[keep], ys[keep]
    return x, y, _face_h(x, y)

def t_facedots(arr, t, d, ctx):
    """Face ID: 'flood' (IR wash), 'dots' (projected grid), 'depth' (dots shift with depth -> 3D map)."""
    mode = d.get("mode", "dots"); c = (CX, 760); RX, RY = 230, 300
    x, y, h = _face_grid()
    if mode == "flood":
        k = smooth(t / .8)
        m, p = disc(300, 90); comp(arr, m, c[0] - p, c[1] - p, ctx.accent, .10 * k)
        sy = c[1] - RY + (t * 420) % (2 * RY)                                   # scan line
        for i in range(len(x)):
            px, py = c[0] + x[i] * RX, c[1] + y[i] * RY
            v = .25 + .75 * h[i]; near = max(0, 1 - abs(py - sy) / 60)
            dot(arr, px, py, 2.2 + 1.2 * near, ctx.accent, k * (.18 + .3 * v + .5 * near))
        icon(arr, "sun-dim", c[0], c[1] - RY - 90, 72, G4, enter(t, .2, .7)[0])
    else:
        r0 = ctx.at(d.get("at"), .05); grow = expo((t - r0) / 1.4) * 1.5
        warp = expo((t - ctx.at(d.get("warp_at"), .3)) / 1.6) if mode == "depth" else 0.0
        for i in range(len(x)):
            rr = math.hypot(x[i], y[i])
            if rr > grow: continue
            a = smooth((grow - rr) / .25)
            px = c[0] + x[i] * RX + warp * 80 * (h[i] - .4); py = c[1] + y[i] * RY
            col = mixc(G3, ctx.accent, .25 + .75 * h[i])
            dot(arr, px, py, 2.0 + 1.6 * h[i] + 1.2 * h[i] * warp, col, a * (.3 + .7 * h[i]))
        la, lb, ldy = enter(t, r0 + .3, .8, 12, 8)
        if mode == "dots": label(arr, "30,000+ infrared dots", CX, 400 + ldy, G4, la, 26, blur=lb)
        else: label(arr, "Closer dots shift more", CX, 400 + ldy, G4, la, 26, blur=lb)

def t_heat(arr, t, d, ctx):
    """Phone thermal view: 'chip' hot spot, 'sources' (chip / battery / screen), 'throttle' (temperature up, speed down)."""
    mode = d.get("mode", "chip"); a, _, dy = enter(t, 0, .7, 30, 0)
    if mode == "throttle":
        tt = ctx.at(d.get("at"), .1); k = expo((t - tt) / 2.2)
        for i, (lab, v0, v1, colr) in enumerate((("Temperature", .35, .92, ctx.accent), ("Speed", .95, .55, INK))):
            y = 640 + i * 230 + dy; v = v0 + (v1 - v0) * k
            label(arr, lab, 130, y - 60, G4, a, 24, "l")
            comp(arr, rr_mask(740, 18, 9), 130, y, (40, 40, 38), a)
            w = max(18, int(740 * v)); comp(arr, rr_mask(w, 18, 9), 130, y, colr, a)
            text(arr, ("↑" if i == 0 else "↓"), 900, y - 54, "Medium", 44, colr, a * smooth((t - tt) / .6), "r")
        return
    pw, ph = 420, 840; x0, y0 = CX - pw // 2, 360 + dy
    glass(arr, (x0, y0, x0 + pw, y0 + ph), 70, a, tint=.04)
    spots = [("chip", (CX + 40, y0 + 230), 1.0, "Chip"), ("battery", (CX, y0 + 560), .7, "Battery"), ("screen", (CX, y0 + 420), .35, "Screen")]
    show = ["chip"] if mode == "chip" else ["chip", "battery", "screen"]
    ats = d.get("at", [None] * 3)
    for i, (k, p, power, txt) in enumerate(spots):
        if k not in show: continue
        ts = ctx.at(ats[i] if i < len(ats) else None, .05 + .4 * i)
        e = expo((t - ts) / 1.0)
        if e <= 0: continue
        pulse = .85 + .15 * math.sin(t * 3 + i)
        if k == "screen":
            comp(arr, rr_mask(pw - 40, ph - 40, 52), x0 + 20, y0 + 20, ctx.accent, .07 * e * pulse * a)
        else:
            r = int(150 * power); m, pp = disc(r, r * .55); comp(arr, m, p[0] - pp, p[1] - pp, ctx.accent, .55 * e * pulse * a)
            dot(arr, p[0], p[1], 9, INK if k == "chip" else ctx.accent, e * a)
            for j in range(2):                                   # isotherm rings drifting outwards
                q = ((t * .5 + j * .5) % 1.0); rr = int(r * (.6 + 1.2 * q))
                cv2.circle(arr, (int(p[0]), int(p[1])), rr, mixc((20, 20, 20), ctx.accent, .5 * (1 - q) * e * a), 2, cv2.LINE_AA)
        if mode == "sources" or k == "chip":
            la = smooth((t - ts - .2) / .4) * a
            side = 1 if k != "battery" else -1
            lx = x0 + pw + 30 if side > 0 else x0 - 30
            label(arr, txt, lx, p[1], ctx.accent if k == "chip" else G4, la, 24, "l" if side > 0 else "r")

TEMPLATES = {"hook": t_hook, "number": t_number, "big_number": t_number, "versus": t_versus, "globe": t_globe,
             "signal": t_signal, "flow": t_flow, "diagram": t_flow, "rings": t_rings, "list": t_list,
             "insight": t_insight, "didyouknow": t_insight, "chart": t_chart, "reveal": t_reveal, "cell": t_cell, "wall": t_wall, "section": t_section, "facedots": t_facedots, "heat": t_heat}
NO_CAPTIONS = {"hook", "reveal"}            # these already show the spoken words as the headline

def _ats(d, key, n): a = d.get(key) or []; return [a[i] if i < len(a) else None for i in range(n)]
EVENTS = {
    "hook": lambda d, c: [(c.at(s.get("at"), 0.0), "tick") for s in d["shots"][1:]],
    "number": lambda d, c: [(c.at(d.get("at"), .03), "tick"), (c.at(d.get("at"), .03) + d.get("dur", 1.1) * .6, "chime")],
    "versus": lambda d, c: [(c.at(d.get("a_at"), .02), "tick"), (c.at(d.get("b_at"), .4), "tick")],
    "globe": lambda d, c: [(c.at(d.get("at"), .05) + d.get("dur", 1.6) * .7, "chime")] + ([(c.at(d.get("sub_at"), 99.0), "tick")] if d.get("sub") else []),
    "signal": lambda d, c: [(c.at(x, .2 + .35 * i), "tick") for i, x in enumerate(_ats(d, "row_at", len(d.get("rows", []))))],
    "flow": lambda d, c: [(c.at(x, .05 + i * .3), "tick") for i, x in enumerate(_ats(d, "at", len(d["nodes"])))],
    "rings": lambda d, c: [(c.at(x, .05 + i * .3), "tick") for i, x in enumerate(_ats(d, "at", 3)[d.get("start", 0):d.get("show", 3)])]
                          + ([(c.at(d.get("you_at"), .7), "chime")] if d.get("show", 3) > 1 else []),
    "list": lambda d, c: [(c.at(x, .15 + i * .3), "tick") for i, x in enumerate(_ats(d, "at", len(d["items"])))],
    "insight": lambda d, c: [(.25, "tick")],
    "chart": lambda d, c: [(c.at(x, .1 + i * .7 / len(d["bars"])), "tick") for i, x in enumerate(_ats(d, "at", len(d["bars"])))],
    "reveal": lambda d, c: [(0.0, "chime")],
    "cell": lambda d, c: [(.05, "tick")] + ([(c.at(d.get("crust_at"), .08) + .5, "tick")] if d.get("mode") == "trap" else []),
    "wall": lambda d, c: [(.05, "tick")],
    "section": lambda d, c: [(c.at(d.get(k + "_at"), dt), "tick") for k, dt in (("fibers", 0.0), ("steel", .25), ("copper", .5), ("sheath", .75))][:4],
    "facedots": lambda d, c: [(c.at(d.get("at"), .05), "tick")] + ([(c.at(d.get("warp_at"), .3), "chime")] if d.get("mode") == "depth" else []),
    "heat": lambda d, c: [(c.at(x, .05 + .4 * i), "tick") for i, x in enumerate(_ats(d, "at", 1 if d.get("mode", "chip") == "chip" else 3))],
}
for a, b in (("big_number", "number"), ("diagram", "flow"), ("didyouknow", "insight")): EVENTS[a] = EVENTS[b]

# 3D hero objects each template gets by default (a beat can override with data["objects"])
def objects_for(vt, d):
    if "objects" in d: return d["objects"]
    if vt == "globe": return [dict(type="globe", cx=CX, cy=950, w=820, h=820, sats=d.get("count", 24), at=d.get("at", .05))]
    if vt == "signal": return [dict(type="satellite", cx=360, cy=560, w=780, h=560, at=0.0, dist=6.3),
                               dict(type="phone", cx=790, cy=1040, w=300, h=470, at=.15, dist=4.4)]
    return []

def object_jobs(beat, accent):
    """Job dicts for studio3d.cjs (frames at FPS, global time T so rotation is continuous across cuts)."""
    ctx = Ctx(accent, beat["D"], beat["words"], beat["T0"], beat["index"]); jobs = []
    for o in beat["objects"]:
        j = {k: v for k, v in o.items() if k not in ("cx", "cy", "at", "dir")}
        j.update(fps=FPS, frames=beat["frames"], T0=beat["T0"], accent=accent if isinstance(accent, str) else "#%02X%02X%02X" % accent)
        if o["type"] == "globe":
            d = beat["data"]; j.update(reveal_at=ctx.at(d.get("at"), .05), reveal_dur=d.get("dur", 1.6))
        jobs.append(j)
    return jobs

# ---------------------------------------------------------------- captions
def caption_chunks(words, size=72, maxn=3):
    chunks, cur = [], []
    for w in words:
        trial = " ".join(x["text"] for x in cur + [w])
        if cur and (len(cur) >= maxn or tw(trial, "Medium", size, -.01) > CAP_W - 40):
            chunks.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.,:;?!]$", w["text"]): chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    return chunks

def draw_captions(arr, t, chunks, accent, D, size=72):
    cur = None
    for i, ch in enumerate(chunks):
        if t >= ch[0]["start"] - .06: cur = i
    if cur is None: return
    ch = chunks[cur]
    if cur + 1 < len(chunks) and t >= chunks[cur + 1][0]["start"] - .06: return
    toks = [(w["text"], bool(w.get("key"))) for w in ch]
    sz = size
    while sz > 48 and tw(" ".join(w for w, _ in toks), "Medium", sz, -.01) > CAP_W: sz -= 4
    st = [enter(t, w["start"] - .06, .4, 12, 7) for w in ch]
    words_line(arr, toks, OUT_CX, CAP_Y, "Medium", sz, -.01, INK, accent, st, shadow=.75)

# ---------------------------------------------------------------- camera, brand, outro, frame
def camera(arr, t, D, idx, motion=True):
    """Slow constant camera + re-centre: the design space (centre CX) lands centred on the frame (OUT_CX),
    scaled by FIT, so the composition is symmetric on screen and survives side-cropping on tall phones."""
    k = t / max(D, 1e-3)                                     # slow, constant: alternate push-in / pull-back
    z = 1.0 + .032 * k if idx % 2 == 0 else 1.032 - .032 * k
    dx = (12 * k - 6) * (1 if idx % 3 else -1); dy = -8 * k
    if not motion: z, dx, dy = 1.0, 0.0, 0.0
    s = z * FIT
    M = np.float32([[s, 0, OUT_CX - s * CX + dx], [0, s, (1 - s) * 800 + dy]])
    return cv2.warpAffine(arr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

# ---------------------------------------------------------------- brand: Quiet Circuit mark (geometry = branding/brandkit.py mark_B)
MARK_RING, MARK_R = (44, 46), 29                 # 100-unit box
MARK_TAIL = [(44 + 29 * math.cos(math.pi / 4), 46 + 29 * math.sin(math.pi / 4)), (72, 74), (83, 74)]
MARK_PAD, MARK_PAD_R = (89, 74), 6.2

def mark_mask(size, ring=1.0, tail=1.0, sw=8.6, ss=4):
    """Ring + trace of the mark (ink part) as a float mask, size x size px; ring/tail = draw-on progress 0..1."""
    S = int(size * ss); k = S / 100; m = np.zeros((S, S), np.uint8); th = max(1, int(round(sw * k)))
    if ring > 0:   # starts and ends where the trace leaves the ring (45°), drawn clockwise
        cv2.ellipse(m, (int(MARK_RING[0] * k), int(MARK_RING[1] * k)), (int(MARK_R * k),) * 2, 0, 45, 45 + 360 * min(ring, 1), 255, th, cv2.LINE_AA)
    if tail > 0:
        segs = list(zip(MARK_TAIL[:-1], MARK_TAIL[1:])); L = sum(math.dist(p, q) for p, q in segs); left = L * min(tail, 1)
        for p, q in segs:
            if left <= 0: break
            l = math.dist(p, q); f = min(1, left / l); left -= l
            e = (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
            cv2.line(m, (int(p[0] * k), int(p[1] * k)), (int(e[0] * k), int(e[1] * k)), 255, th, cv2.LINE_AA)
    return cv2.resize(m, (int(size), int(size)), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

@lru_cache(8)
def _mark_static(size): return mark_mask(size)

def draw_mark(arr, x, y, size, accent, alpha=1.0, ring=1.0, tail=1.0, pad=1.0, glow=.8, ink=INK):
    """Mark with its box top-left at (x, y). The pad (the 'light') takes the video's category accent."""
    m = _mark_static(int(size)) if ring >= 1 and tail >= 1 else mark_mask(size, ring, tail)
    comp(arr, m, x, y, ink, alpha)
    if pad > 0:
        s = size / 100; dot(arr, x + MARK_PAD[0] * s, y + MARK_PAD[1] * s, MARK_PAD_R * s, accent, alpha * pad, glow=glow * pad)

def logo(arr, accent, alpha=1.0):
    """Discreet brand, top-centre inside the safe zone (never cut by side-cropping): small mark + QUIET CIRCUIT."""
    if alpha <= 0.004: return
    ms, gap = 32, 10; total = ms * .95 + gap + tw("QUIET CIRCUIT", "SemiBold", 21, .24); x0 = OUT_CX - total / 2
    draw_mark(arr, x0 - ms * .15, 300 - ms * .47, ms, accent, .92 * alpha, glow=.5)
    text(arr, "QUIET CIRCUIT", x0 + ms * .95 + gap, 300, "SemiBold", 21, G4, .85 * alpha, "l", "c", .24)

OUTRO = .85
def outro_k(t, D): return clamp((t - (D - OUTRO)) / OUTRO)

def outro(arr, t, D, accent):
    """Signature close on every Short: the scene blurs into #0A0A0A, then the Quiet Circuit mark draws itself
    (ring -> trace) and its node lights up in the category accent, with the wordmark underneath."""
    k = outro_k(t, D)
    if k <= 0: return arr
    e = smooth(k / .42)
    small = cv2.resize(arr, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    bl = cv2.resize(cv2.GaussianBlur(small, (0, 0), 1 + 5 * e), (W, H), interpolation=cv2.INTER_LINEAR)
    out = cv2.addWeighted(arr, 1 - e, bl, e, 0)
    out = np.ascontiguousarray(cv2.addWeighted(out, 1 - e, np.full_like(out, BG), e, 0))
    size = 220; x, y = OUT_CX - size * .52, 870 - size / 2
    ring = expo((k - .12) / .42); tail = smooth((k - .5) / .14); pad = smooth((k - .6) / .12)
    if ring > 0: draw_mark(out, x, y, size, accent, smooth((k - .1) / .1), ring, tail, pad, glow=.9)
    a, b, dy = enter(k * OUTRO, .62 * OUTRO, .5, 12, 8)
    text(out, "QUIET CIRCUIT", OUT_CX, 1080 + dy, "Medium", 30, G4, a, "m", "c", .3, b)
    return out

def render_frame(beat, t, bg, accent, captions=True, cam=True, finish=True, fi=0):
    acc = hexrgb(accent) if isinstance(accent, str) else accent
    d = beat["data"]; ctx = Ctx(acc, beat["D"], beat["words"], beat["T0"], beat["index"])
    strength = d.get("glow_strength", 1.0)
    if beat["visual_type"] == "reveal": strength = 1.0 + .9 * smooth(t / 1.2)
    arr = bg.frame(beat["T0"] + t, tuple(d.get("glow", (CX, 820))), strength)
    for o in beat.get("objects", []):
        if not o.get("dir"): continue
        a, b, dy = enter(t, ctx.at(o.get("at"), 0.0) if o.get("at") is not None else 0.0, 1.0, 40, 16)
        if beat["index"] == 0 and o.get("at") is None: a, b, dy = 1.0, 0.0, 0.0
        fr = min(beat["frames"] - 1, int(round(t * FPS)))
        layer(arr, obj_frame(o["dir"], fr), o["cx"], o["cy"] + dy, a * o.get("alpha", 1.0), b)
    TEMPLATES[beat["visual_type"]](arr, t, d, ctx)
    arr = camera(arr, t, beat["D"], beat["index"], motion=cam)
    if captions and beat["visual_type"] not in NO_CAPTIONS and not d.get("no_captions"):
        draw_captions(arr, t, beat["chunks"], acc, beat["D"])
    k = outro_k(t, beat["D"]) if beat.get("outro") else 0.0
    if k > 0: arr = outro(arr, t, beat["D"], acc)
    if finish:
        logo(arr, acc, 1 - smooth(k / .35))
        arr = bg.finish(arr, fi)
    return arr

def cover(beat, obj_rgba, bg, accent, big, small=None):
    """Thumbnail: same layout for every Short — hero object, small label, 2–4 word headline, brand logo."""
    acc = hexrgb(accent)
    arr = bg.frame(0.0, (CX, 1060), 1.4)
    if obj_rgba is not None:
        h, w = obj_rgba.shape[:2]; s = min(1.0, 900 / max(h, w)) * .95
        layer(arr, cv2.resize(obj_rgba, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA), CX, 1180)
    ctx = Ctx(acc, 1.0, [], 0, 0); y = 620
    size = headline(arr, 99.0, ctx, big, y, 170)
    top = y - (len(_lines(big)) - 1) * size * 1.08 / 2            # centre of the first headline line
    if small: label(arr, small, CX, top - size * CAP / 2 - 64, G4, 1, 32)
    arr = camera(arr, 0, 1, 0, motion=False)
    logo(arr, acc)
    return bg.finish(arr, 0)

def safe_overlay(im):
    im = im.copy(); d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, W, SAFE_T), fill=(255, 0, 0, 60)); d.rectangle((0, H - SAFE_B, W, H), fill=(255, 0, 0, 60))
    d.rectangle((W - SAFE_R, 0, W, H), fill=(255, 0, 0, 60))
    return im
