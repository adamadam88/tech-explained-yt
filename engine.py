"""Vertical Shorts engine (1080x1920) for "Tech, Explained".

Shapes are drawn with OpenCV (antialiased) on a numpy RGB frame, text with Pillow.
Grew out of render.py (horizontal GPS sample): same palette, easing, Earth/satellite/phone art.

Every template is `fn(cv, t, data, ctx)`:
  cv   Canvas (numpy frame + lazy PIL view)
  t    seconds since the beat started
  data the beat's `data` dict from script.json
  ctx  Ctx: palette, beat duration, word timings (for syncing to the narration)
and has a matching `EVENTS[name](data, ctx)` -> [(t, sfx)] so sound effects land on the animation.
"""
import math, re
from functools import lru_cache
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
# YouTube Shorts UI safe zone: nothing important in top 250, bottom 420, right 140.
SAFE_T, SAFE_B, SAFE_R, SAFE_L = 250, 420, 140, 60
X0, X1 = SAFE_L, W - SAFE_R          # 60 .. 940
CX = (X0 + X1) // 2                  # 500  (content centre, shifted left of the buttons)
MAXW = 800                           # usable width for visual text (camera zoom adds a few %)
CAP_W = 860                          # captions are drawn after the camera, so they can use more
Y0, Y1 = SAFE_T, H - SAFE_B          # 250 .. 1500
CAP_Y = 1330                         # caption line (inside safe zone, below the visuals)

FD = "/usr/share/fonts/opentype/inter/"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

@lru_cache(None)
def F(w, s):
    s = max(8, int(s))
    return ImageFont.truetype(FD + f"{'InterDisplay' if s > 60 else 'Inter'}-{w}.otf", s)

@lru_cache(None)
def FM(s): return ImageFont.truetype(MONO, int(s))

WH = (242, 246, 252); GR = (140, 155, 182); DK = (8, 12, 22)
EARTH = (35, 95, 170); LAND = (60, 170, 120)
PALETTES = {
    "cyan":   dict(bg=(10, 16, 32), bg2=(20, 32, 60),  a=(64, 210, 255),  b=(255, 170, 60)),
    "mint":   dict(bg=(8, 20, 28),  bg2=(14, 40, 52),  a=(80, 240, 180),  b=(255, 110, 150)),
    "violet": dict(bg=(14, 12, 34), bg2=(32, 24, 68),  a=(170, 130, 255), b=(190, 255, 90)),
    "gold":   dict(bg=(12, 16, 30), bg2=(28, 34, 60),  a=(255, 206, 70),  b=(70, 200, 255)),
    "coral":  dict(bg=(10, 18, 34), bg2=(24, 36, 64),  a=(255, 120, 90),  b=(90, 230, 230)),
}

# ---------------------------------------------------------------- maths
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return x * x * (3 - 2 * x)
def ease_out(x): x = clamp(x); return 1 - (1 - x) ** 3
def back(x, s=1.8):
    x = clamp(x); x -= 1; return 1 + x * x * ((s + 1) * x + s)
def fade(t, a, b): return ease((t - a) / (b - a)) if b > a else float(t >= a)
def mix(c1, c2, k): return tuple(int(c1[i] + (c2[i] - c1[i]) * clamp(k)) for i in range(3))
def appear(t, t0, dur=0.28):
    """(alpha, scale) for an element popping in at t0 with overshoot."""
    if t < t0: return 0.0, 0.0
    x = (t - t0) / dur
    return ease(x * 1.6), 0.6 + 0.4 * back(x)

# ---------------------------------------------------------------- text
KW = re.compile(r"\*([^*]+)\*")
def strip_kw(s): return s.replace("*", "")
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

def tsize(s, font, stroke=0):
    x0, y0, x1, y1 = font.getbbox(s, stroke_width=stroke)
    return x1 - x0, y1 - y0

def fit(s, weight, maxsize, maxw, minsize=24):
    size = maxsize
    while size > minsize and F(weight, size).getlength(s) > maxw: size -= 4
    return size

def text(im, xy, s, font, fill=WH, alpha=1.0, anchor="mm", stroke=0, stroke_fill=DK, shadow=0):
    """Alpha-aware text: renders a cropped mask and pastes it (cheap at 1080x1920)."""
    if alpha <= 0.01 or not s: return
    x, y = xy
    pad = stroke + shadow + 4
    bx0, by0, bx1, by1 = font.getbbox(s, anchor=anchor, stroke_width=stroke)
    w, h = bx1 - bx0 + 2 * pad, by1 - by0 + 2 * pad
    ox, oy = int(x + bx0 - pad), int(y + by0 - pad)
    org = (x - ox, y - oy)
    a255 = int(255 * clamp(alpha))
    if shadow:
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text(org, s, font=font, anchor=anchor, fill=255, stroke_width=stroke)
        m = m.point(lambda v: v * a255 * 0.55 / 255)
        im.paste((0, 0, 0), (ox + shadow, oy + shadow), m)
    if stroke:
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text(org, s, font=font, anchor=anchor, fill=255, stroke_width=stroke)
        if a255 < 255: m = m.point(lambda v: v * a255 // 255)
        im.paste(stroke_fill, (ox, oy), m)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text(org, s, font=font, anchor=anchor, fill=255)
    if a255 < 255: m = m.point(lambda v: v * a255 // 255)
    im.paste(fill, (ox, oy), m)

def rich_line(im, d, cx, cy, toks, weight, size, col, kcol, alpha=1.0, mode="color", reveal=None, stroke=0):
    """Centered line of words; keyword words in kcol (mode 'color') or on a highlight bar ('box').
    reveal: list of per-word (alpha, scale) or None."""
    font = F(weight, size); sp = font.getlength(" ") + (26 if mode == "box" else 6)
    widths = [font.getlength(w) for w, _ in toks]
    total = sum(widths) + sp * (len(toks) - 1)
    x = cx - total / 2
    for i, ((w, k), ww) in enumerate(zip(toks, widths)):
        a, sc = (alpha, 1.0) if reveal is None else (reveal[i][0] * alpha, reveal[i][1])
        wc = x + ww / 2
        if a > 0.01:
            f = F(weight, size * sc) if abs(sc - 1) > 0.01 else font
            if k and mode == "box":
                bw, bh = ww * sc + 34, size * 1.12 * sc
                d.rounded_rectangle((wc - bw / 2, cy - bh / 2 + 4, wc + bw / 2, cy + bh / 2 + 4), int(16 * sc),
                                    fill=kcol + (int(255 * a),))
                text(im, (wc, cy), w, f, DK, a)
            else:
                text(im, (wc, cy), w, f, kcol if k else col, a, stroke=stroke)
        x += ww + sp

def wrap(s, font, maxw):
    lines, cur = [], ""
    for w in s.split():
        nxt = (cur + " " + w).strip()
        if font.getlength(strip_kw(nxt)) <= maxw or not cur: cur = nxt
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

# ---------------------------------------------------------------- canvas / drawing helpers
class Canvas:
    def __init__(self, arr): self.arr = arr; self._im = None
    def pil(self):
        if self._im is None:
            self._im = Image.fromarray(self.arr); self.d = ImageDraw.Draw(self._im, "RGBA")
        return self._im
    def result(self): return self._im if self._im is not None else Image.fromarray(self.arr)

def overlay(img, alpha, draw, bbox=None):
    """Real alpha blend of whatever `draw(roi_img, offset)` paints, restricted to bbox for speed."""
    if alpha <= 0.01: return
    x0, y0, x1, y1 = (0, 0, W, H) if bbox is None else bbox
    x0, y0 = max(0, int(x0)), max(0, int(y0)); x1, y1 = min(W, int(x1)), min(H, int(y1))
    if x1 <= x0 or y1 <= y0: return
    roi = img[y0:y1, x0:x1]; ov = roi.copy(); draw(ov, (-x0, -y0))
    cv2.addWeighted(ov, alpha, roi, 1 - alpha, 0, dst=roi)

def P(p, o=(0, 0)): return (int(p[0] + o[0]), int(p[1] + o[1]))

def ring_burst(img, c, t, t0, col, r0=80, r1=420, dur=0.6, th=6):
    x = (t - t0) / dur
    if 0 <= x <= 1:
        r = int(r0 + (r1 - r0) * ease_out(x))
        overlay(img, 0.8 * (1 - x), lambda o, off: cv2.circle(o, P(c, off), r, col, th, cv2.LINE_AA),
                (c[0] - r - th, c[1] - r - th, c[0] + r + th, c[1] + r + th))

def dashed_ring(img, c, r, t, col, n=28, speed=0.4, th=5):
    for k in range(n):
        a0 = k * 360 / n + t * speed * 57.3
        cv2.ellipse(img, P(c), (int(r), int(r)), a0, 0, 360 / n * 0.55, col, th, cv2.LINE_AA)

# ---------------------------------------------------------------- icons (reused + new)
def earth(img, c, r, t=0.0):
    cv2.circle(img, P(c), int(r + 18), (30, 60, 110), -1, cv2.LINE_AA)
    cv2.circle(img, P(c), int(r), EARTH, -1, cv2.LINE_AA)
    x0, y0 = int(c[0] - r - 2), int(c[1] - r - 2); x1, y1 = int(c[0] + r + 3), int(c[1] + r + 3)
    roi = img[max(0, y0):y1, max(0, x0):x1]; keep = roi.copy()
    for dx, dy, rx, ry, ang in [(-.35, -.2, .32, .22, 20), (.3, .15, .25, .35, -15), (-.1, .45, .2, .12, 0),
                                (.25, -.45, .2, .1, 10), (-.9, .1, .22, .3, 5)]:
        dx = ((dx + t * 0.12 + 1.3) % 2.6) - 1.3
        cv2.ellipse(img, (int(c[0] + dx * r), int(c[1] + dy * r)), (int(rx * r), int(ry * r)), ang, 0, 360, LAND, -1, cv2.LINE_AA)
    mask = np.zeros(roi.shape[:2], np.uint8)
    cv2.circle(mask, (int(c[0] - max(0, x0)), int(c[1] - max(0, y0))), int(r), 255, -1, cv2.LINE_AA)
    m = (mask.astype(np.float32) / 255)[..., None]
    roi[:] = (roi * m + keep * (1 - m)).astype(np.uint8)
    # terminator shading
    overlay(img, 0.35, lambda o, off: cv2.ellipse(o, P((c[0] + r * .35, c[1]), off), (int(r * .75), int(r)), 0, -90, 90, (5, 10, 25), -1, cv2.LINE_AA),
            (c[0] - r, c[1] - r, c[0] + r, c[1] + r))

def satellite(img, p, s=1.0, col=(64, 210, 255)):
    x, y = p
    for sx in (-1, 1):
        cv2.rectangle(img, (int(x + sx * 26 * s), int(y - 14 * s)), (int(x + sx * 72 * s), int(y + 14 * s)), (70, 110, 200), -1, cv2.LINE_AA)
        for k in range(1, 3):
            xx = int(x + sx * (26 + 15 * k) * s); cv2.line(img, (xx, int(y - 14 * s)), (xx, int(y + 14 * s)), (40, 70, 140), 2, cv2.LINE_AA)
    cv2.rectangle(img, (int(x - 22 * s), int(y - 22 * s)), (int(x + 22 * s), int(y + 22 * s)), col, -1, cv2.LINE_AA)
    cv2.line(img, (int(x), int(y + 22 * s)), (int(x), int(y + 38 * s)), (200, 210, 225), max(2, int(3 * s)), cv2.LINE_AA)
    cv2.circle(img, (int(x), int(y + 40 * s)), max(3, int(6 * s)), (200, 210, 225), -1, cv2.LINE_AA)

def phone(img, p, s=1.0, screen=(15, 25, 45), dot=(255, 170, 60)):
    x, y = p; w, h = 52 * s, 98 * s
    cv2.rectangle(img, (int(x - w), int(y - h)), (int(x + w), int(y + h)), (205, 214, 228), -1, cv2.LINE_AA)
    cv2.rectangle(img, (int(x - w + 8 * s), int(y - h + 12 * s)), (int(x + w - 8 * s), int(y + h - 14 * s)), screen, -1, cv2.LINE_AA)
    cv2.circle(img, (int(x), int(y - 6 * s)), int(15 * s), dot, -1, cv2.LINE_AA)
    cv2.circle(img, (int(x), int(y + 18 * s)), int(4 * s), dot, -1, cv2.LINE_AA)

def clock(img, c, r, t, col, hand=(255, 170, 60), speed=2.4):
    cv2.circle(img, P(c), int(r), (30, 45, 75), -1, cv2.LINE_AA); cv2.circle(img, P(c), int(r), col, max(3, int(r / 22)), cv2.LINE_AA)
    for k in range(12):
        a = k * math.pi / 6
        p1 = (int(c[0] + r * .82 * math.cos(a)), int(c[1] + r * .82 * math.sin(a)))
        p2 = (int(c[0] + r * .68 * math.cos(a)), int(c[1] + r * .68 * math.sin(a)))
        cv2.line(img, p1, p2, GR, max(2, int(r / 40)), cv2.LINE_AA)
    a = -math.pi / 2 + t * speed
    cv2.line(img, P(c), (int(c[0] + r * .75 * math.cos(a)), int(c[1] + r * .75 * math.sin(a))), hand, max(3, int(r / 20)), cv2.LINE_AA)
    a2 = -math.pi / 2 + t * speed / 12
    cv2.line(img, P(c), (int(c[0] + r * .5 * math.cos(a2)), int(c[1] + r * .5 * math.sin(a2))), WH, max(3, int(r / 16)), cv2.LINE_AA)
    cv2.circle(img, P(c), max(4, int(r / 14)), hand, -1, cv2.LINE_AA)

def chip(img, c, s, col):
    x, y = c; h = 70 * s
    for k in range(-3, 4):
        o = int(k * 18 * s)
        for dx, dy in ((0, -1), (0, 1)):
            cv2.line(img, (x + o, int(y + dy * h)), (x + o, int(y + dy * (h + 22 * s))), GR, max(2, int(5 * s)), cv2.LINE_AA)
        cv2.line(img, (int(x - h), y + o), (int(x - h - 22 * s), y + o), GR, max(2, int(5 * s)), cv2.LINE_AA)
        cv2.line(img, (int(x + h), y + o), (int(x + h + 22 * s), y + o), GR, max(2, int(5 * s)), cv2.LINE_AA)
    cv2.rectangle(img, (int(x - h), int(y - h)), (int(x + h), int(y + h)), (35, 45, 70), -1, cv2.LINE_AA)
    cv2.rectangle(img, (int(x - h * .55), int(y - h * .55)), (int(x + h * .55), int(y + h * .55)), col, -1, cv2.LINE_AA)

def wifi(img, c, s, col, t):
    x, y = c
    for k in range(3):
        on = (t * 2.5 - k * .3) % 1.5 < 1.0
        cv2.ellipse(img, (x, y), (int((40 + 38 * k) * s),) * 2, 0, 225, 315, col if on else GR, max(3, int(12 * s)), cv2.LINE_AA)
    cv2.circle(img, (x, y), int(12 * s), col, -1, cv2.LINE_AA)

def battery(img, c, s, col, level):
    x, y = c; w, h = 60 * s, 105 * s
    cv2.rectangle(img, (int(x - 22 * s), int(y - h - 14 * s)), (int(x + 22 * s), int(y - h)), GR, -1, cv2.LINE_AA)
    cv2.rectangle(img, (int(x - w), int(y - h)), (int(x + w), int(y + h)), GR, max(3, int(8 * s)), cv2.LINE_AA)
    top = y + h - 10 * s - (2 * h - 20 * s) * clamp(level)
    cv2.rectangle(img, (int(x - w + 10 * s), int(top)), (int(x + w - 10 * s), int(y + h - 10 * s)), col, -1, cv2.LINE_AA)

def lock(img, c, s, col):
    x, y = c
    cv2.ellipse(img, (x, int(y - 30 * s)), (int(42 * s), int(52 * s)), 0, 180, 360, GR, max(3, int(14 * s)), cv2.LINE_AA)
    cv2.line(img, (int(x - 42 * s), int(y - 30 * s)), (int(x - 42 * s), int(y)), GR, max(3, int(14 * s)), cv2.LINE_AA)
    cv2.line(img, (int(x + 42 * s), int(y - 30 * s)), (int(x + 42 * s), int(y)), GR, max(3, int(14 * s)), cv2.LINE_AA)
    cv2.rectangle(img, (int(x - 68 * s), int(y)), (int(x + 68 * s), int(y + 100 * s)), col, -1, cv2.LINE_AA)
    cv2.circle(img, (x, int(y + 45 * s)), int(13 * s), DK, -1, cv2.LINE_AA)

def icon(img, name, c, s, pal, t):
    c = P(c)
    if name == "phone": phone(img, c, s, dot=pal["b"])
    elif name == "satellite": satellite(img, c, s, pal["a"])
    elif name == "globe": earth(img, c, 90 * s, t)
    elif name == "clock": clock(img, c, 95 * s, t, pal["a"], pal["b"])
    elif name == "chip": chip(img, c, s, pal["a"])
    elif name == "wifi": wifi(img, (c[0], c[1] + int(50 * s)), s, pal["a"], t)
    elif name == "battery": battery(img, c, s, pal["a"], 0.5 + 0.5 * math.sin(t * 2))
    elif name == "lock": lock(img, c, s, pal["a"])

# ---------------------------------------------------------------- background
class Background:
    def __init__(self, pal, seed=0):
        self.pal = pal
        g = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        grad = np.array(pal["bg"], np.float32) * (1 - g) + np.array(pal["bg2"], np.float32) * g
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        glow = np.exp(-(((xx - CX) / 520) ** 2 + ((yy - 760) / 650) ** 2))[..., None]
        grad = grad * (1 - .22 * glow) + np.array(pal["a"], np.float32) * .22 * glow * .45 + grad * .22 * glow * .55
        vig = 1 - 0.45 * np.clip(((xx - W / 2) / (W * .75)) ** 2 + ((yy - H / 2) / (H * .75)) ** 2, 0, 1)[..., None]
        self.base = np.clip(grad * vig, 0, 255).astype(np.uint8)
        self.grid = mix(pal["bg2"], WH, .07)
        rng = np.random.default_rng(seed)
        self.parts = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(10, 45), rng.uniform(1.5, 4.0), rng.uniform(.15, .45))
                      for _ in range(38)]

    def frame(self, T):
        img = self.base.copy(); step = 108; off = int(T * 22) % step
        for x in range(-step, W + step, step): cv2.line(img, (x + off // 2, 0), (x + off // 2, H), self.grid, 1)
        for y in range(-step, H + step, step): cv2.line(img, (0, y + off), (W, y + off), self.grid, 1)
        for x, y, v, r, k in self.parts:
            yy = (y - T * v) % H; xx = x + 14 * math.sin(T * .6 + y)
            cv2.circle(img, (int(xx), int(yy)), int(r), mix(self.pal["bg2"], self.pal["a"], k), -1, cv2.LINE_AA)
        return img

# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, pal, D, words, T0=0.0, index=0):
        self.pal, self.D, self.words, self.T0, self.index = pal, D, words, T0, index
    def at(self, spec, default=0.0):
        """int -> start of word #n, float<=1 -> fraction of beat, float>1 -> seconds, str -> first word containing it."""
        if spec is None: return default
        if isinstance(spec, bool): return default
        if isinstance(spec, int):
            return self.words[min(spec, len(self.words) - 1)]["start"] if self.words else default
        if isinstance(spec, float): return spec * self.D if spec <= 1 else spec
        s = str(spec).lower()
        for w in self.words:
            if s in w["text"].lower(): return w["start"]
        return default
    def word_times(self, n):
        """Start times for n display words spread over the narration words."""
        if not self.words: return [i * self.D / max(1, n) * .8 for i in range(n)]
        m = len(self.words)
        return [self.words[min(m - 1, int(i * m / n))]["start"] for i in range(n)]

# ---------------------------------------------------------------- templates
def _lines_block(cv, t, ctx, lines, maxsize, ytop, ybot, weight="Black", mode="box", sync=True):
    im = cv.pil(); d = cv.d; pal = ctx.pal
    toks = [tokens(l) for l in lines]
    # every line gets its own size (short punchy lines become huge), capped at maxsize
    sizes = [fit(" ".join(w for w, _ in tk), weight, maxsize, MAXW - 30 * len(tk) - (40 if any(k for _, k in tk) else 0)) for tk in toks]
    lhs = [s * 1.18 for s in sizes]; total = sum(lhs); y = (ytop + ybot) / 2 - total / 2
    n = sum(len(tk) for tk in toks); times = ctx.word_times(n) if sync else [0.0] * n; k = 0
    for tk, size, lh in zip(toks, sizes, lhs):
        rev = []
        for _ in tk: rev.append(appear(t, times[k] - 0.04, 0.22)); k += 1
        rich_line(im, d, CX, y + lh / 2, tk, weight, size, WH, pal["a"], mode=mode, reveal=rev)
        y += lh
    return sizes

def t_hook(cv, t, data, ctx):
    pal = ctx.pal; img = cv.arr
    c = (CX, 1130)
    for i in range(3):
        r = int(150 + i * 110 + (t * 90) % 110)
        cv2.circle(img, c, r, mix(pal["bg2"], pal["a"], .25 - i * .06), 3, cv2.LINE_AA)
    s = 1.35 * (1 + .06 * math.sin(t * 5))
    icon(img, data.get("icon", "phone"), (c[0], c[1] + 8 * math.sin(t * 3)), s, pal, t)
    im = cv.pil()
    if data.get("badge"):
        a, sc = appear(t, ctx.at(data.get("badge_at"), .25))
        bx, by = c[0] + 105, c[1] - 120
        cv.d.ellipse((bx - 58 * sc, by - 58 * sc, bx + 58 * sc, by + 58 * sc), fill=pal["b"] + (int(255 * a),))
        text(im, (bx, by + 2), data["badge"], F("Black", 80 * sc), DK, a)
    _lines_block(cv, t, ctx, data["lines"], data.get("size", 150), 300, 900)

def t_big_number(cv, t, data, ctx):
    pal = ctx.pal; img = cv.arr; c = (CX, 640)
    t0 = ctx.at(data.get("at"), .05); dur = data.get("dur", 1.0)
    p = ease_out((t - t0) / dur); done = t0 + dur
    dashed_ring(img, c, 330, t, mix(pal["bg2"], pal["a"], .55), th=6)
    cv2.ellipse(img, c, (300, 300), -90, 0, 360 * p, pal["a"], 10, cv2.LINE_AA)
    ring_burst(img, c, t, done, pal["b"], 300, 520)
    im = cv.pil()
    v = data["value"] * p + data.get("from", 0) * (1 - p); dec = data.get("decimals", 0)
    s = f"{data.get('prefix', '')}{v:,.{dec}f}{data.get('suffix', '')}"
    final = f"{data.get('prefix', '')}{data['value']:,.{dec}f}{data.get('suffix', '')}"
    size = fit(final, "Black", data.get("size", 230), 520)
    a, sc = appear(t, done, .3); sc = 1 + .12 * (1 - ease((t - done) / .3)) if t > done else 1
    text(im, (c[0], c[1]), s, F("Black", size * sc), pal["a"] if t < done else WH, fade(t, t0 - .1, t0 + .1), shadow=6)
    la = fade(t, ctx.at(data.get("label_at"), done - .3), ctx.at(data.get("label_at"), done - .3) + .25)
    if data.get("label"):
        text(im, (CX, 1030 - 18 * (1 - la)), data["label"], F("ExtraBold", fit(data["label"], "ExtraBold", 64, MAXW)), WH, la)
    if data.get("sub"):
        sa = fade(t, done + .2, done + .5)
        text(im, (CX, 1110), data["sub"], F("SemiBold", fit(data["sub"], "SemiBold", 44, MAXW)), GR, sa)

def _card(cv, box, col, a, label, value, vcol, slide=0):
    x0, y0, x1, y1 = box; x0 += slide; x1 += slide; im = cv.pil(); d = cv.d
    d.rounded_rectangle((x0, y0, x1, y1), 36, fill=mix(DK, col, .12) + (int(235 * a),), outline=col + (int(255 * a),), width=5)
    cxx = (x0 + x1) / 2
    text(im, (cxx, y0 + 70), label, F("ExtraBold", fit(label, "ExtraBold", 50, x1 - x0 - 80)), GR, a)
    vs = fit(value, "Black", 150, x1 - x0 - 80)
    text(im, (cxx, (y0 + y1) / 2 + 40), value, F("Black", vs), vcol, a, shadow=5)

def t_versus(cv, t, data, ctx):
    pal = ctx.pal; A, B = data["a"], data["b"]
    ta = ctx.at(data.get("a_at"), .02); tb = ctx.at(data.get("b_at"), .45)
    pa = ease_out((t - ta) / .35); pb = ease_out((t - tb) / .35)
    if data.get("title"):
        cv.pil(); text(cv._im, (CX, 300), data["title"], F("ExtraBold", fit(data["title"], "ExtraBold", 58, MAXW)), pal["a"], fade(t, 0, .3))
    _card(cv, (90, 360, 910, 690), pal["a"], fade(t, ta, ta + .2), A["label"], A["value"], WH, slide=-500 * (1 - pa))
    _card(cv, (90, 800, 910, 1130), pal["b"], fade(t, tb, tb + .2), B["label"], B["value"], pal["b"], slide=500 * (1 - pb))
    a, sc = appear(t, (ta + tb) / 2, .3)
    if a > 0:
        r = 62 * sc * (1 + .05 * math.sin(t * 8)); y = 745
        cv.d.ellipse((CX - r, y - r, CX + r, y + r), fill=WH + (int(255 * a),))
        text(cv._im, (CX, y + 2), "VS", F("Black", 52 * sc), DK, a)

def t_globe(cv, t, data, ctx):
    pal = ctx.pal; img = cv.arr; c = (CX, 640); R = 200
    zoom = 1 + .06 * t / ctx.D
    n = data.get("count", 24); planes = 6
    t0 = ctx.at(data.get("at"), .05); p = ease_out((t - t0) / data.get("dur", 1.6))
    shown = int(round(n * p))
    sats = []
    for i in range(n):
        pl = (i % planes) * math.pi / planes; ph = (i // planes) * 2 * math.pi / math.ceil(n / planes) + pl * 1.7
        a = ph + t * .45; x, y = 370 * zoom * math.cos(a), 135 * zoom * math.sin(a)
        cp, sp = math.cos(pl), math.sin(pl)
        sats.append((c[0] + x * cp - y * sp, c[1] + x * sp + y * cp, math.sin(a), i < shown))
    for k in range(planes):
        cv2.ellipse(img, c, (int(370 * zoom), int(135 * zoom)), math.degrees(k * math.pi / planes), 0, 360, mix(pal["bg2"], pal["a"], .3), 2, cv2.LINE_AA)
    for x, y, z, on in sats:
        if z < 0 and on: cv2.circle(img, (int(x), int(y)), 7, mix(pal["bg2"], pal["a"], .5), -1, cv2.LINE_AA)
    earth(img, c, R, t)
    if data.get("pin"):
        pa = fade(t, ctx.at(data.get("pin_at"), .5), ctx.at(data.get("pin_at"), .5) + .3)
        if pa > 0:
            pp = (c[0] - 40, c[1] - 30 - int(10 * math.sin(t * 6)))
            cv2.circle(img, (pp[0], pp[1] - 40), 26, pal["b"], -1, cv2.LINE_AA)
            cv2.fillPoly(img, [np.array([(pp[0] - 22, pp[1] - 28), (pp[0] + 22, pp[1] - 28), (pp[0], pp[1] + 10)])], pal["b"], cv2.LINE_AA)
            cv2.circle(img, (pp[0], pp[1] - 40), 10, DK, -1, cv2.LINE_AA)
    for x, y, z, on in sats:
        if z >= 0 and on:
            cv2.circle(img, (int(x), int(y)), 13, mix(DK, pal["a"], .3), -1, cv2.LINE_AA)
            cv2.circle(img, (int(x), int(y)), 8, pal["a"], -1, cv2.LINE_AA)
    im = cv.pil()
    s = f"{shown}{data.get('suffix', '') if shown == n else ''}"
    text(im, (CX, 1040), s, F("Black", 170), WH, fade(t, t0, t0 + .15), shadow=6)
    if data.get("label"):
        text(im, (CX, 1150), data["label"], F("ExtraBold", fit(data["label"], "ExtraBold", 56, MAXW)), pal["a"], fade(t, t0 + .2, t0 + .5))
    if data.get("sub"):
        sa = fade(t, ctx.at(data.get("sub_at"), .55), ctx.at(data.get("sub_at"), .55) + .3)
        sz = fit(data["sub"], "Black", 60, MAXW - 60)
        tw = F("Black", sz).getlength(data["sub"])
        cv.d.rounded_rectangle((CX - tw / 2 - 26, 290 - 44, CX + tw / 2 + 26, 290 + 44), 22, fill=pal["b"] + (int(255 * sa),))
        text(im, (CX, 292), data["sub"], F("Black", sz), DK, sa)

def t_signal(cv, t, data, ctx):
    pal = ctx.pal; img = cv.arr; sp = (250, 400); pp = (770, 800)
    for k in range(7):
        ph = t * 1.2 - k * .4
        if ph < 0: continue
        x = (ph % 2.8) / 2.8; r = int(60 + x * 1100)
        cv2.circle(img, sp, r, mix(pal["bg2"], pal["a"], .7 * (1 - x)), 4, cv2.LINE_AA)
    # dotted path + travelling packet
    n = 18
    for k in range(n):
        q = k / n; cv2.circle(img, (int(sp[0] + (pp[0] - sp[0]) * q), int(sp[1] + (pp[1] - sp[1]) * q)), 4, GR, -1, cv2.LINE_AA)
    q = (t * .9) % 1
    cv2.circle(img, (int(sp[0] + (pp[0] - sp[0]) * q), int(sp[1] + (pp[1] - sp[1]) * q)), 14, pal["b"], -1, cv2.LINE_AA)
    satellite(img, (sp[0], sp[1] + int(6 * math.sin(t * 3))), 1.5, pal["a"])
    phone(img, pp, 1.25, dot=pal["b"])
    im = cv.pil(); d = cv.d
    lines = data.get("lines", [])
    if lines:
        ba = fade(t, ctx.at(data.get("at"), .05), ctx.at(data.get("at"), .05) + .25)
        y0 = 1010; y1 = y0 + 70 + 78 * len(lines)
        d.rounded_rectangle((90, y0, 910, y1), 28, fill=mix(DK, pal["a"], .08) + (int(240 * ba),), outline=pal["a"] + (int(255 * ba),), width=4)
        text(im, (130, y0 + 42), data.get("title", "BROADCAST"), FM(34), pal["a"], ba, anchor="lm")
        ms = int((t * 1000) % 1000)
        for i, ln in enumerate(lines):
            ats = data.get("line_at", [None] * len(lines))
            ta = ctx.at(ats[i] if i < len(ats) else None, .2 + .3 * i)
            la = fade(t, ta, ta + .15)
            s = ln.replace("{ms}", f"{ms:03d}")
            text(im, (130 + 40 * (1 - la), y0 + 115 + 78 * i), s, FM(fit(s, "Bold", 46, 740) * .96), WH if i % 2 == 0 else pal["b"], la, anchor="lm")

def t_flow(cv, t, data, ctx):
    pal = ctx.pal; im = cv.pil(); d = cv.d
    nodes = data["nodes"]; n = len(nodes); top, bot = 320, 1130
    hgt = min(170, (bot - top) / n - 70); gap = ((bot - top) - n * hgt) / max(1, n - 1)
    ats = data.get("at", [None] * n); times = [ctx.at(ats[i] if i < len(ats) else None, .05 + i * .28) for i in range(n)]
    for i, node in enumerate(nodes):
        y = top + i * (hgt + gap); a, sc = appear(t, times[i])
        if i > 0:
            aa = fade(t, times[i] - .2, times[i])
            ya, yb = y - gap + 12, y - 12
            ym = ya + (yb - ya) * aa
            if aa > 0:
                d.line((CX, ya, CX, ym), fill=GR + (255,), width=8)
                if aa >= 1: d.polygon([(CX - 22, yb - 26), (CX + 22, yb - 26), (CX, yb)], fill=GR + (255,))
        if a <= 0: continue
        last = i == n - 1 or t < times[i + 1]
        col = pal["b"] if i == n - 1 else pal["a"]
        w = 780 * sc; h = hgt * sc; cy = y + hgt / 2
        d.rounded_rectangle((CX - w / 2, cy - h / 2, CX + w / 2, cy + h / 2), int(h / 2),
                            fill=(col if last else mix(DK, col, .15)) + (int(255 * a),), outline=col + (int(255 * a),), width=5)
        s = node if isinstance(node, str) else node["text"]
        text(im, (CX, cy + 2), s, F("Black", fit(s, "Black", 70, 680) * sc), DK if last else WH, a)

def t_rings(cv, t, data, ctx):
    pal = ctx.pal; img = cv.arr; tgt = (CX, 720)
    sats = [(200, 420), (830, 470), (520, 1140)]; cols = [pal["a"], pal["b"], (190, 140, 255)]
    show = data.get("show", 3); start = data.get("start", 0)
    ats = data.get("at", [None] * 3)
    for i in range(show):
        c = sats[i]; r = int(math.dist(c, tgt))
        if i < start: a = 1.0
        else:
            ta = ctx.at(ats[i] if i < len(ats) else None, .05 + (i - start) * .3); a = ease_out((t - ta) / .7)
        if a <= 0: continue
        overlay(img, .13 * a, lambda o, off, c=c, r=r, col=cols[i]: cv2.circle(o, P(c, off), r, col, -1, cv2.LINE_AA),
                (c[0] - r, c[1] - r, c[0] + r, c[1] + r))
        cv2.ellipse(img, c, (r, r), -90 + i * 40, 0, 360 * a, cols[i], 6, cv2.LINE_AA)
        satellite(img, c, .85, cols[i])
    im = None
    if show == 1:   # "you could be anywhere on this circle"
        c = sats[0]; r = int(math.dist(c, tgt))
        for k in range(3):
            ang = t * 1.3 + k * 2.1
            p = (int(c[0] + r * math.cos(ang)), int(c[1] + r * math.sin(ang)))
            cv2.circle(img, p, 16, WH, -1, cv2.LINE_AA)
            im = cv.pil(); text(im, (p[0], p[1] - 46), "?", F("Black", 60), WH, fade(t, .2, .5), stroke=5)
    else:
        ty = ctx.at(data.get("you_at"), .7); a = fade(t, ty, ty + .2)
        if a > 0:
            pulse = 1 + .25 * math.sin(t * 7)
            cv2.circle(img, tgt, int(22 * pulse), WH, -1, cv2.LINE_AA)
            ring_burst(img, tgt, t, ty, WH, 20, 260, .7)
            im = cv.pil()
            text(im, (tgt[0], tgt[1] - 90), data.get("label", "YOU"), F("Black", 96 * (1 + .25 * (1 - ease((t - ty) / .3)))), WH, a, stroke=8)
    if data.get("title"):
        im = cv.pil(); text(im, (CX, 300), data["title"], F("ExtraBold", fit(data["title"], "ExtraBold", 56, MAXW)), WH, fade(t, 0, .3), stroke=6)

def t_list(cv, t, data, ctx):
    pal = ctx.pal
    if data.get("icon"):
        ia, isc = appear(t, ctx.at(data.get("icon_at"), .5), .35)
        if ia > .2: icon(cv.arr, data["icon"], (CX, 1080 + 8 * math.sin(t * 3)), 1.2 * isc, pal, t)
    im = cv.pil(); d = cv.d
    title = data.get("title", "")
    ta = fade(t, 0, .25)
    tsz = fit(title, "Black", 84, MAXW)
    text(im, (CX, 360), title, F("Black", tsz), pal["a"], ta, shadow=5)
    tw = F("Black", tsz).getlength(title) * ease_out(t / .5)
    d.rounded_rectangle((CX - tw / 2, 425, CX + tw / 2, 437), 6, fill=pal["b"] + (int(255 * ta),))
    items = data["items"]; ats = data.get("at", [None] * len(items))
    for i, it in enumerate(items):
        ti = ctx.at(ats[i] if i < len(ats) else None, .15 + i * .3)
        a = fade(t, ti, ti + .2); dx = 300 * (1 - ease_out((t - ti) / .35))
        if a <= 0: continue
        y = 600 + i * 210
        d.rounded_rectangle((90 + dx, y - 85, 910 + dx, y + 85), 34, fill=mix(DK, pal["a"], .1) + (int(230 * a),))
        tk = tokens(it); s = " ".join(w for w, _ in tk)
        sz = fit(s, "Black", 84, 720)
        rich_line(im, d, CX + dx, y, tk, "Black", sz, WH, pal["b"], alpha=a)

def t_didyouknow(cv, t, data, ctx):
    pal = ctx.pal; img = cv.arr
    a, sc = appear(t, .02, .35)
    box = (90, 330, 910, 1140); cx, cy = CX, (box[1] + box[3]) / 2
    w, h = (box[2] - box[0]) * sc, (box[3] - box[1]) * sc
    ic = (CX, int(cy - 170 * sc))
    im = cv.pil(); d = cv.d
    d.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), 44, fill=mix(DK, pal["a"], .1) + (int(240 * a),), outline=pal["a"] + (int(255 * a),), width=5)
    cv.arr = np.asarray(im).copy(); cv._im = None; img = cv.arr
    if a > .3: icon(img, data.get("icon", "clock"), ic, 1.25 * sc, pal, t)
    im = cv.pil(); d = cv.d
    k = data.get("kicker", "DID YOU KNOW?"); ks = 46; kw = F("Black", ks).getlength(k)
    ky = cy - h / 2 - 2; ka, ksc = appear(t, .25, .3)
    d.rounded_rectangle((CX - kw / 2 - 30, ky - 42, CX + kw / 2 + 30, ky + 42), 42, fill=pal["b"] + (int(255 * ka),))
    text(im, (CX, ky + 2), k, F("Black", ks * ksc), DK, ka)
    f = F("Black", data.get("size", 92)); lines = wrap(data["text"], f, 720)
    y = cy + 140 - (len(lines) - 1) * 55
    n = sum(len(l.split()) for l in lines); times = ctx.word_times(n); j = 0
    for ln in lines:
        tk = tokens(ln); rev = []
        for _ in tk: rev.append(appear(t, max(.3, times[j]) - .05, .22)); j += 1
        rich_line(im, d, CX, y, tk, "Black", data.get("size", 92), WH, pal["b"], alpha=a, reveal=rev, mode="box")
        y += 110

def t_chart(cv, t, data, ctx):
    pal = ctx.pal; im = cv.pil(); d = cv.d
    title = data.get("title", "")
    text(im, (CX, 330), title, F("ExtraBold", fit(title, "ExtraBold", 58, MAXW)), WH, fade(t, 0, .3))
    bars = data["bars"]; n = len(bars); vmax = max(v for _, v in bars) * 1.1
    bx0, bx1, base, top = 120, 900, 1110, 470
    slot = (bx1 - bx0) / n; bw = slot * .62
    d.line((bx0 - 20, base, bx1 + 10, base), fill=GR + (255,), width=5)
    for k in range(1, 4):
        yy = base - (base - top) * k / 4
        for xx in range(bx0, bx1, 34): d.line((xx, yy, xx + 16, yy), fill=mix(DK, GR, .35) + (255,), width=2)
    ats = data.get("at", [None] * n); unit = data.get("unit", "")
    for i, (lab, v) in enumerate(bars):
        ti = ctx.at(ats[i] if i < len(ats) else None, .1 + i * .7 / n); p = ease_out((t - ti) / .5)
        if p <= 0: continue
        x = bx0 + slot * i + (slot - bw) / 2; hh = (base - top) * v / vmax * p
        col = pal["b"] if i == n - 1 else pal["a"]
        d.rounded_rectangle((x, base - hh, x + bw, base), 14, fill=col + (255,))
        cur = v * p; s = (f"{cur:,.0f}" if v >= 10 or v == int(v) else f"{cur:.1f}") + unit
        text(im, (x + bw / 2, base - hh - 42), s, F("Black", fit(s, "Black", 52, slot - 6)), WH, min(1, p * 3))
        text(im, (x + bw / 2, base + 46), lab, F("Bold", fit(lab, "Bold", 38, slot - 4)), GR, min(1, p * 3))

def t_reveal(cv, t, data, ctx):
    pal = ctx.pal; img = cv.arr; c = (CX, 700)
    n = 16; rot = t * .35
    for k in range(n):
        a0 = rot + k * 2 * math.pi / n
        pts = np.array([c, (c[0] + 1500 * math.cos(a0), c[1] + 1500 * math.sin(a0)),
                        (c[0] + 1500 * math.cos(a0 + .12), c[1] + 1500 * math.sin(a0 + .12))], np.int32)
        cv2.fillPoly(img, [pts], mix(pal["bg2"], pal["a"], .12), cv2.LINE_AA)
    ring_burst(img, c, t, .02, pal["a"], 40, 700, .8, 10)
    if data.get("icon"): icon(img, data["icon"], (CX, 1100), 1.2, pal, t)
    _lines_block(cv, t, ctx, data["lines"], data.get("size", 170), 330, 950, mode=data.get("mode", "color"))

TEMPLATES = {"hook": t_hook, "big_number": t_big_number, "versus": t_versus, "globe": t_globe, "signal": t_signal,
             "diagram": t_flow, "flow": t_flow, "rings": t_rings, "list": t_list, "didyouknow": t_didyouknow,
             "chart": t_chart, "reveal": t_reveal}
NO_CAPTIONS = {"hook", "reveal"}   # these templates already show the narration as giant synced text

def _n(lst): return lst if isinstance(lst, list) else []
EVENTS = {
    "hook": lambda d, c: [(0.0, "impact")] + ([(c.at(d.get("badge_at"), .25), "pop")] if d.get("badge") else []),
    "big_number": lambda d, c: [(c.at(d.get("at"), .05), "riser_short"), (c.at(d.get("at"), .05) + d.get("dur", 1.0), "pop")],
    "versus": lambda d, c: [(c.at(d.get("a_at"), .02), "pop"), (c.at(d.get("b_at"), .45), "pop")],
    "globe": lambda d, c: [(c.at(d.get("at"), .05) + d.get("dur", 1.6), "pop")] + ([(c.at(d.get("sub_at"), .55), "click")] if d.get("sub") else []),
    "signal": lambda d, c: [(c.at(x, .2 + .3 * i), "click") for i, x in enumerate(_n(d.get("line_at")) or [None] * len(d.get("lines", [])))],
    "diagram": lambda d, c: [(c.at(x, .05 + i * .28), "pop") for i, x in enumerate(_n(d.get("at")) or [None] * len(d["nodes"]))],
    "rings": lambda d, c: [(c.at(x, .05 + i * .3), "pop") for i, x in enumerate((_n(d.get("at")) or [None] * 3)[d.get("start", 0):d.get("show", 3)])]
                          + ([(c.at(d.get("you_at"), .7), "ding")] if d.get("show", 3) > 1 else []),
    "list": lambda d, c: [(c.at(x, .15 + i * .3), "click") for i, x in enumerate(_n(d.get("at")) or [None] * len(d["items"]))],
    "didyouknow": lambda d, c: [(0.02, "pop"), (0.25, "click")],
    "chart": lambda d, c: [(c.at(x, .1 + i * .7 / len(d["bars"])), "click") for i, x in enumerate(_n(d.get("at")) or [None] * len(d["bars"]))],
    "reveal": lambda d, c: [(0.0, "impact")],
}
EVENTS["flow"] = EVENTS["diagram"]

# ---------------------------------------------------------------- captions (word by word)
def caption_chunks(words, maxw=CAP_W - 60, size=92, maxn=3):
    f = F("Black", size); chunks, cur = [], []
    for i, w in enumerate(words):
        trial = " ".join(x["text"] for x in cur + [w]).upper()
        if cur and (len(cur) >= maxn or f.getlength(trial) > maxw):
            chunks.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.,:;?!]$", w["text"]): chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    return chunks

def draw_captions(im, t, chunks, pal, D, size=92):
    if not chunks: return
    cur = None
    for i, ch in enumerate(chunks):
        if t >= ch[0]["start"] - .03: cur = i
    if cur is None: return
    ch = chunks[cur]
    end = chunks[cur + 1][0]["start"] if cur + 1 < len(chunks) else D
    if t > end + .05: return
    d = ImageDraw.Draw(im, "RGBA")
    words = [w["text"].upper() for w in ch]
    sz = size
    while sz > 50 and F("Black", sz).getlength(" ".join(words)) + 20 * len(words) > CAP_W - 40: sz -= 4
    f = F("Black", sz); sp = f.getlength(" ") + 20
    ws = [f.getlength(w) for w in words]; total = sum(ws) + sp * (len(ws) - 1); x = CX - total / 2
    for w, ww, info in zip(words, ws, ch):
        if t >= info["start"] - .03:
            active = t < info["end"] + .08 and (info is ch[-1] or t < ch[ch.index(info) + 1]["start"])
            k = clamp((t - info["start"] + .03) / .12)
            sc = 1 + .14 * (1 - ease(k)) if active else 1.0
            col = pal["b"] if info.get("key") else (pal["a"] if active else WH)
            text(im, (x + ww / 2, CAP_Y), w, F("Black", sz * sc), col, 1.0, stroke=9, stroke_fill=DK, shadow=7)
        x += ww + sp

# ---------------------------------------------------------------- camera + transitions + frame
TRANSITIONS = ["punch", "slide", "whip", "flash", "zoomout"]

def camera(arr, t, D, kind, seed):
    z = 1.0 + .04 * ease(t / D)
    dx = 10 * math.sin(t * .9 + seed); dy = 8 * math.cos(t * .7 + seed); rot = .6 * math.sin(t * .5 + seed)
    x = clamp(t / .28)
    if kind == "punch": z += .16 * (1 - ease_out(x))
    elif kind == "zoomout": z -= .12 * (1 - ease_out(x)); z = max(z, .9)
    elif kind == "slide": dy += 260 * (1 - ease_out(x))
    elif kind == "whip": dx += 420 * (1 - ease_out(x)) * (1 if seed % 2 else -1)
    M = cv2.getRotationMatrix2D((CX, 760), rot, z); M[0, 2] += dx; M[1, 2] += dy
    out = cv2.warpAffine(arr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if kind == "whip" and x < 1:
        k = int(1 + 60 * (1 - x)); out = cv2.blur(out, (k, 1))
    if kind == "slide" and x < 1:
        k = int(1 + 40 * (1 - x)); out = cv2.blur(out, (1, k))
    return out

def render_frame(beat, t, bg, pal, captions=True, cam=True):
    """beat: dict(visual_type, data, words, D, T0, index, transition, chunks)."""
    ctx = Ctx(pal, beat["D"], beat["words"], beat["T0"], beat["index"])
    cv = Canvas(bg.frame(beat["T0"] + t))
    TEMPLATES[beat["visual_type"]](cv, t, beat["data"], ctx)
    arr = np.asarray(cv.result()) if cv._im is not None else cv.arr
    if cam: arr = camera(np.ascontiguousarray(arr), t, beat["D"], beat.get("transition", "punch"), beat["index"])
    if beat.get("transition") == "flash" and t < .2:
        arr = cv2.addWeighted(arr, 1, np.full_like(arr, pal["a"]), .45 * (1 - t / .2), 0)
    im = Image.fromarray(arr)
    if captions and beat["visual_type"] not in NO_CAPTIONS and not beat["data"].get("no_captions"):
        draw_captions(im, t, beat["chunks"], pal, beat["D"])
    return im

def safe_overlay(im):
    """Review helper: draws the YouTube UI no-go zones."""
    im = im.copy(); d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, W, SAFE_T), fill=(255, 0, 0, 60)); d.rectangle((0, H - SAFE_B, W, H), fill=(255, 0, 0, 60))
    d.rectangle((W - SAFE_R, 0, W, H), fill=(255, 0, 0, 60))
    return im
