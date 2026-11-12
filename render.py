"""Tech, Explained — visual engine.

Draws 1920x1080 frames with OpenCV (antialiased shapes) + Pillow (text sprites).
Every scene = theme background + one template + Ken Burns + entry transition,
then word-by-word captions, chapter tag and progress bar on top.

Templates (visual_type): hook_title, globe, question, big_number, versus, broadcast,
flow, circles, tiles, top_list, quote, timeline, chart, clock, noise, outro.
Elements are synced to the voice with "cue": a word from the narration (its spoken
start time, from faster-whisper), optionally "word+0.4", or a number of seconds.
"""
import math, os, re, subprocess
from functools import lru_cache
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1920, 1080, 30
FD = "/usr/share/fonts/opentype/inter/"
MONO = "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-ExtraBold.ttf"
WHITE = (242, 245, 250)

THEMES = {
    "navy":    dict(bg1=(9, 15, 30),  bg2=(18, 32, 58), grid=(24, 38, 64), acc=(64, 210, 255), acc2=(255, 170, 60), land=(80, 200, 255)),
    "plum":    dict(bg1=(20, 9, 32),  bg2=(46, 18, 66), grid=(50, 28, 72), acc=(255, 96, 200), acc2=(255, 214, 90), land=(255, 120, 210)),
    "teal":    dict(bg1=(5, 22, 25),  bg2=(10, 46, 48), grid=(18, 56, 58), acc=(70, 240, 180), acc2=(255, 200, 70), land=(90, 240, 190)),
    "amber":   dict(bg1=(24, 16, 8),  bg2=(52, 34, 12), grid=(62, 44, 22), acc=(255, 186, 64), acc2=(96, 200, 255), land=(255, 190, 90)),
    "crimson": dict(bg1=(26, 7, 12),  bg2=(56, 14, 24), grid=(68, 26, 36), acc=(255, 84, 96), acc2=(255, 222, 120), land=(255, 110, 120)),
}
MUTE = (160, 172, 195)


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def ease(x): x = clamp(x); return x * x * (3 - 2 * x)
def ease_out(x): x = clamp(x); return 1 - (1 - x) ** 3
def back_out(x):
    x = clamp(x); c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2
def fade(t, a, b): return ease((t - a) / (b - a)) if b > a else float(t >= a)
def pop(dt, dur=0.38):
    """alpha, scale for an element that appears at dt=0."""
    if dt < 0: return 0.0, 0.7
    return ease(dt / 0.16), 0.72 + 0.28 * back_out(dt / dur)
def mix(c1, c2, k): return tuple(int(a + (b - a) * k) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- text sprites
@lru_cache(maxsize=256)
def font(weight, size, mono=False):
    if mono: return ImageFont.truetype(MONO, size)
    fam = "InterDisplay" if size >= 64 else "Inter"
    return ImageFont.truetype(FD + f"{fam}-{weight}.otf", size)

def tw(s, size, weight="Bold", mono=False): return font(weight, size, mono).getlength(s)

def fit(s, size, max_w, weight="Bold", mono=False, min_size=18):
    while size > min_size and tw(s, size, weight, mono) > max_w: size -= 2
    return size

def wrap(s, size, max_w, weight="Bold", mono=False):
    words, lines, cur = s.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if cur and tw(nxt, size, weight, mono) > max_w: lines.append(cur); cur = w
        else: cur = nxt
    if cur: lines.append(cur)
    return lines

def fit_wrap(s, size, max_w, max_lines, weight="Bold", mono=False):
    """Largest size so the text wraps into <= max_lines lines that all fit max_w."""
    while size > 20:
        ls = wrap(s, size, max_w, weight, mono)
        if len(ls) <= max_lines and all(tw(l, size, weight, mono) <= max_w for l in ls): return size, ls
        size -= 2
    return size, wrap(s, size, max_w, weight, mono)

_SPR = {}
def sprite(s, size, weight="Bold", color=WHITE, mono=False, glow=None):
    key = (s, size, weight, color, mono, glow)
    if key in _SPR: return _SPR[key]
    if len(_SPR) > 3000: _SPR.clear()
    f = font(weight, size, mono); asc, desc = f.getmetrics()
    w = int(math.ceil(f.getlength(s))); h = asc + desc
    pad = max(6, int(size * (0.45 if glow else 0.1)))
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), s, font=f, fill=tuple(color) + (255,))
    if glow:
        g = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).text((pad, pad), s, font=f, fill=tuple(glow) + (150,))
        g = g.filter(ImageFilter.GaussianBlur(size * 0.14))
        im = Image.alpha_composite(g, im)
    r = (np.asarray(im).copy(), pad, w, h)
    _SPR[key] = r; return r

def blit(img, arr, x0, y0, alpha=1.0):
    if alpha <= 0.003: return
    h, w = arr.shape[:2]; Hh, Ww = img.shape[:2]
    X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(Ww, x0 + w), min(Hh, y0 + h)
    if X1 <= X0 or Y1 <= Y0: return
    a = arr[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0]
    al = a[..., 3:4].astype(np.float32) * (alpha / 255.0)
    reg = img[Y0:Y1, X0:X1].astype(np.float32)
    reg += (a[..., :3].astype(np.float32) - reg) * al
    img[Y0:Y1, X0:X1] = reg.astype(np.uint8)

def put(img, arr_meta, x, y, anchor="mm", alpha=1.0, scale=1.0):
    arr, pad, w, h = arr_meta
    if scale != 1.0:
        if scale <= 0.01: return
        arr = cv2.resize(arr, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        pad, w, h = pad * scale, w * scale, h * scale
    ox = {"l": 0, "m": w / 2, "r": w}[anchor[0]]
    oy = {"t": 0, "m": h / 2, "b": h}[anchor[1]]
    blit(img, arr, int(round(x - ox - pad)), int(round(y - oy - pad)), alpha)

def txt(img, s, x, y, size, weight="Bold", color=WHITE, alpha=1.0, anchor="mm", scale=1.0, glow=None, mono=False, max_w=None):
    if not s or alpha <= 0: return 0
    if max_w: size = fit(s, size, max_w, weight, mono)
    sp = sprite(s, size, weight, tuple(color), mono, tuple(glow) if glow else None)
    put(img, sp, x, y, anchor, alpha, scale)
    return sp[2] * scale

_PAN = {}
def panel_sprite(w, h, r, fill, outline=None, width=0):
    key = (w, h, r, fill, outline, width)
    if key in _PAN: return _PAN[key]
    if len(_PAN) > 600: _PAN.clear()
    S = 2
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w * S - 1, h * S - 1), r * S, fill=fill,
                                         outline=outline, width=width * S)
    arr = np.asarray(im.resize((w, h), Image.LANCZOS)).copy()
    _PAN[key] = arr; return arr

def panel(img, x0, y0, x1, y1, r=24, fill=(0, 0, 0, 140), outline=None, width=0, alpha=1.0):
    w, h = int(x1 - x0), int(y1 - y0)
    if w < 4 or h < 4: return
    q = lambda c: tuple(int(v) for v in c) if c else None
    blit(img, panel_sprite(w, h, int(min(r, h // 2, w // 2)), q(fill), q(outline), width), int(x0), int(y0), alpha)

def pill(img, s, x, y, size, color, fg=WHITE, alpha=1.0, anchor="m", weight="Bold", dot=None, scale=1.0, fill=None, max_w=1500):
    size = fit(s, size, max_w, weight)
    w = tw(s, size, weight) + (size * 0.9 if dot else 0); padx, h = size * 0.75, size * 1.7
    w, h, padx = w * scale, h * scale, padx * scale
    x0 = {"l": x, "m": x - w / 2 - padx, "r": x - w - 2 * padx}[anchor]
    panel(img, x0, y - h / 2, x0 + w + 2 * padx, y + h / 2, h / 2, fill if fill else (12, 16, 28, 215),
          tuple(color) + (255,), max(2, int(3 * scale)), alpha)
    tx = x0 + padx
    if dot:
        cv2_alpha(img, alpha, lambda o: cv2.circle(o, (int(tx + size * 0.28 * scale), int(y)), int(size * 0.22 * scale), tuple(dot), -1, cv2.LINE_AA),
                  (int(tx), int(y - size * scale), int(tx + size * scale), int(y + size * scale)))
        tx += size * 0.9 * scale
    txt(img, s, tx, y, size, weight, fg, alpha, "lm", scale)
    return w + 2 * padx

def cv2_alpha(img, alpha, fn, box=None):
    """Run a cv2 draw function with transparency (optionally only inside box)."""
    if alpha <= 0.003: return
    if alpha >= 0.997: fn(img); return
    if box:
        x0, y0, x1, y1 = [int(v) for v in box]; x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(W, x1), min(H, y1)
        if x1 <= x0 or y1 <= y0: return
        sub = img[y0:y1, x0:x1]; ov = np.ascontiguousarray(img).copy()
        fn(ov); cv2.addWeighted(ov[y0:y1, x0:x1], alpha, sub, 1 - alpha, 0, dst=sub)
    else:
        ov = img.copy(); fn(ov); cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, dst=img)


# ---------------------------------------------------------------- backgrounds
@lru_cache(maxsize=8)
def bg_base(theme):
    th = THEMES[theme]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W * 0.35) / W) ** 2 + ((yy - H * 0.2) / H) ** 2)
    k = clamp_arr(d / 1.0)[..., None]
    img = (np.array(th["bg2"], np.float32) * (1 - k) + np.array(th["bg1"], np.float32) * k)
    img = img.astype(np.uint8)
    for x in range(0, W, 96): cv2.line(img, (x, 0), (x, H), th["grid"], 1)
    for y in range(12, H, 96): cv2.line(img, (0, y), (W, y), th["grid"], 1)
    v = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vig = (1 - 0.38 * clamp_arr(v - 0.55) ** 1.2)[..., None]
    return (img.astype(np.float32) * vig).astype(np.uint8)

def clamp_arr(a): return np.clip(a, 0, 1)

@lru_cache(maxsize=8)
def glow_sprite(r, color):
    yy, xx = np.mgrid[-r:r, -r:r].astype(np.float32)
    a = np.clip(1 - np.sqrt(xx ** 2 + yy ** 2) / r, 0, 1) ** 2
    out = np.zeros((2 * r, 2 * r, 4), np.uint8); out[..., :3] = color; out[..., 3] = (a * 255).astype(np.uint8)
    return out

_RNG = np.random.default_rng(7)
PARTS = _RNG.random((70, 4))
def background(theme, tg):
    th = THEMES[theme]; img = bg_base(theme).copy()
    gx = W * (0.5 + 0.35 * math.sin(tg * 0.11)); gy = H * (0.45 + 0.25 * math.cos(tg * 0.083))
    blit(img, glow_sprite(520, th["acc"]), int(gx - 520), int(gy - 520), 0.10)
    dim = mix(th["bg2"], th["acc"], 0.35)
    for px, py, sp, sz in PARTS:
        x = int((px * W + 14 * math.sin(tg * 0.5 + py * 9)) % W)
        y = int((py * H - tg * (8 + 22 * sp)) % H)
        cv2.circle(img, (x, y), 1 + int(sz * 2.2), dim, -1, cv2.LINE_AA)
    return img


# ---------------------------------------------------------------- icons
def rot_rect(img, c, w, h, ang, color):
    box = cv2.boxPoints(((float(c[0]), float(c[1])), (float(w), float(h)), float(ang)))
    cv2.fillConvexPoly(img, np.int32(np.round(box * 4)), color, cv2.LINE_AA, shift=2)

def satellite(img, x, y, s=1.0, col=(64, 210, 255), ang=0.0):
    a = math.radians(ang); dx, dy = math.cos(a), math.sin(a)
    panel_c = (90, 120, 210)
    for sg in (-1, 1):
        cx, cy = x + sg * 58 * s * dx, y + sg * 58 * s * dy
        cv2.line(img, (int(x), int(y)), (int(cx), int(cy)), (180, 190, 210), max(1, int(4 * s)), cv2.LINE_AA)
        rot_rect(img, (cx, cy), 52 * s, 30 * s, ang, panel_c)
        for k in (-1, 1):
            cv2.line(img, (int(cx + k * 9 * s * dx - 15 * s * -dy), int(cy + k * 9 * s * dy - 15 * s * dx)),
                     (int(cx + k * 9 * s * dx + 15 * s * -dy), int(cy + k * 9 * s * dy + 15 * s * dx)), (60, 80, 150), max(1, int(2 * s)), cv2.LINE_AA)
    rot_rect(img, (x, y), 40 * s, 40 * s, ang, col)
    rot_rect(img, (x, y), 22 * s, 22 * s, ang, mix(col, (255, 255, 255), 0.5))

def phone(img, x, y, s=1.0, scr=(15, 25, 45), dot=(255, 170, 60)):
    w, h = 50 * s, 92 * s
    cv2.rectangle(img, (int(x - w), int(y - h)), (int(x + w), int(y + h)), (205, 212, 228), -1, cv2.LINE_AA)
    cv2.rectangle(img, (int(x - w + 8 * s), int(y - h + 14 * s)), (int(x + w - 8 * s), int(y + h - 14 * s)), scr, -1, cv2.LINE_AA)
    cv2.circle(img, (int(x), int(y - 6 * s)), int(13 * s), dot, -1, cv2.LINE_AA)

def map_pin(img, x, y, s, color, t):
    pulse = (t * 1.3) % 1.0
    cv2_alpha(img, 1 - pulse, lambda o: cv2.circle(o, (int(x), int(y)), int(10 + 60 * pulse * s), color, 3, cv2.LINE_AA),
              (x - 90 * s, y - 90 * s, x + 90 * s, y + 90 * s))
    cv2.circle(img, (int(x), int(y)), int(16 * s), (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, (int(x), int(y)), int(11 * s), color, -1, cv2.LINE_AA)


# ---------------------------------------------------------------- dot globe
@lru_cache(maxsize=1)
def land_points():
    from global_land_mask import globe
    n = 16000; i = np.arange(n) + 0.5
    lat = 90 - np.degrees(np.arccos(1 - 2 * i / n)); lon = (np.degrees(np.pi * (1 + 5 ** 0.5) * i) % 360) - 180
    m = globe.is_land(lat, lon)
    return np.radians(lat[m]), np.radians(lon[m])

@lru_cache(maxsize=8)
def sphere_sprite(R, theme):
    th = THEMES[theme]; p = int(R * 0.12); n = 2 * (R + p)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) - (R + p)
    d = np.sqrt(xx ** 2 + yy ** 2) / R
    lx, ly = -0.45, -0.55
    z = np.sqrt(np.clip(1 - d ** 2, 0, 1)); light = np.clip(xx / R * lx + yy / R * ly + z * 0.7, 0, 1)
    base = np.array(mix(th["bg1"], (20, 40, 80), 0.6), np.float32); hi = np.array(mix(th["bg2"], th["acc"], 0.25), np.float32)
    col = base * (1 - light[..., None] * 0.9) + hi * light[..., None] * 0.9
    a = np.where(d <= 1, 1.0, 0.0)
    rim = np.clip(1 - np.abs(d - 1.0) / 0.1, 0, 1) ** 2 * 0.75
    out = np.zeros((n, n, 4), np.float32)
    acc = np.array(th["acc"], np.float32)
    out[..., :3] = np.where(a[..., None] > 0, col * (1 - rim[..., None] * 0.6) + acc * rim[..., None] * 0.6, acc)
    out[..., 3] = np.clip(a + rim * (d > 1), 0, 1) * 255
    edge = np.clip((1.0 - d) * R, 0, 1)  # antialias edge
    out[..., 3] = np.maximum(edge * 255, np.clip(rim * (d > 1), 0, 1) * 255)
    return out.astype(np.uint8)

def globe_frame(img, cx, cy, R, lon0, tilt, theme, t, sats=True, planes=6, pin=None, pin_a=0.0, rays_a=0.0):
    th = THEMES[theme]; tl = math.radians(tilt)
    def view(x, y, z):  # rotate about screen-horizontal axis for tilt; returns depth, sx, sy
        y2 = y; z2 = z * math.cos(tl) - x * math.sin(tl); x2 = x * math.cos(tl) + z * math.sin(tl)
        return x2, cx + y2 * R, cy - z2 * R
    # orbits
    orbit_pts = []
    if sats:
        inc = math.radians(55); k = 1.62
        us = np.linspace(0, 2 * math.pi, 160)
        for p in range(planes):
            raan = math.radians(p * 360 / planes + 10)
            def orb(u):
                x, y, z = np.cos(u), np.sin(u), np.zeros_like(u)
                y, z = y * math.cos(inc), y * math.sin(inc)
                x, y = x * math.cos(raan) - y * math.sin(raan), x * math.sin(raan) + y * math.cos(raan)
                return x * k, y * k, z * k
            ox, oy, oz = orb(us)
            dz, sx, sy = view(ox, oy, oz)
            pts = np.stack([sx, sy], 1)
            cv2.polylines(img, [np.int32(pts * 4)], True, mix(th["bg2"], th["acc"], 0.32), 2, cv2.LINE_AA, shift=2)
            for j in range(4):
                u = np.array([t * 0.16 + j * math.pi / 2 + p * 0.7])
                x, y, z = orb(u); d, sx1, sy1 = view(x, y, z)
                orbit_pts.append((float(d[0]), float(sx1[0]), float(sy1[0]), (pts, dz)))
        for d, sx1, sy1, _ in orbit_pts:
            if d < 0 and (sx1 - cx) ** 2 + (sy1 - cy) ** 2 > R * R: satellite(img, sx1, sy1, 0.32, mix(th["acc"], th["bg1"], 0.4))
    sp = sphere_sprite(R, theme); p = sp.shape[0] // 2
    blit(img, sp, int(cx - p), int(cy - p))
    lat, lon = land_points(); l = lon - math.radians(lon0)
    x, y, z = np.cos(lat) * np.cos(l), np.cos(lat) * np.sin(l), np.sin(lat)
    d, sx, sy = view(x, y, z)
    vis = d > 0.02
    br = np.clip(d[vis], 0, 1)
    for X, Y, b in zip(sx[vis], sy[vis], br):
        cv2.circle(img, (int(X * 4), int(Y * 4)), int((1.2 + 2.0 * b) * R / 300 * 4), mix(th["bg2"], th["land"], 0.35 + 0.65 * b), -1, cv2.LINE_AA, shift=2)
    if sats:
        for pts, dz in {id(o[3][0]): o[3] for o in orbit_pts}.values():
            front = dz > 0
            idx = np.where(front)[0]
            if len(idx) == 0: continue
            segs = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
            for sgm in segs:
                if len(sgm) > 1: cv2.polylines(img, [np.int32(pts[sgm] * 4)], False, mix(th["bg2"], th["acc"], 0.7), 2, cv2.LINE_AA, shift=2)
        for d, sx1, sy1, _ in orbit_pts:
            if d >= 0: satellite(img, sx1, sy1, 0.42, th["acc"], ang=20)
    pin_xy = None
    if pin is not None:
        la, lo = math.radians(pin[0]), math.radians(pin[1] - lon0)
        d, px, py = view(math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
        if d > 0: pin_xy = (px, py)
        if pin_xy and rays_a > 0 and sats:
            front = sorted([o for o in orbit_pts if o[0] > 0], key=lambda o: (o[1] - px) ** 2 + (o[2] - py) ** 2)[:4]
            for d2, sx1, sy1, _ in front:
                ex, ey = px + (sx1 - px) * rays_a, py + (sy1 - py) * rays_a
                cv2.line(img, (int(px), int(py)), (int(ex), int(ey)), th["acc2"], 3, cv2.LINE_AA)
        if pin_xy and pin_a > 0: map_pin(img, px, py, 1.0, th["acc2"], t)
    return pin_xy


# ---------------------------------------------------------------- scene
def norm(w): return re.sub(r"[^a-z0-9]", "", w.lower())

class Scene:
    def __init__(self, job):
        self.job = job; self.spec = job["spec"]; self.d = self.spec.get("data", {})
        self.words = job["words"]; self.D = job["dur"]; self.idx = job["idx"]
        self.theme = self.spec.get("theme", "navy"); self.th = THEMES[self.theme]
        self.acc, self.acc2 = self.th["acc"], self.th["acc2"]
        self._cue = {}

    def cue(self, c, default=None):
        if c is None: return default if default is not None else 0.0
        if isinstance(c, (int, float)): return float(c)
        if c in self._cue: return self._cue[c]
        m = re.match(r"^(.*?)([+-]\d+(\.\d+)?)?$", c.strip()); key, off = m.group(1), float(m.group(2) or 0)
        k = norm(key); val = None
        for w in self.words:
            if norm(w["w"]) == k: val = w["s"]; break
        if val is None:
            for w in self.words:
                if k and norm(w["w"]).startswith(k): val = w["s"]; break
        if val is None:
            print(f"  ! scene {self.idx}: cue '{c}' not found"); val = default if default is not None else self.D * 0.3
        self._cue[c] = val + off; return val + off

    def all_cues(self):
        out = []
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k.endswith("cue") and not isinstance(v, (dict, list)): out.append(self.cue(v))
                    else: walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
        walk(self.d); return sorted(out)

    # ---------- frame
    def frame(self, t):
        tg = self.job["t0"] + t
        img = background(self.theme, tg)
        TEMPLATES[self.spec["visual_type"]](self, img, t)
        img = self.camera(img, t)
        img = self.transition(img, t)
        self.captions(img, t)
        self.chrome(img, t)
        return img

    def camera(self, img, t):
        i = self.idx; D = max(self.D, 1)
        z0, z1 = (1.025, 1.085) if i % 2 == 0 else (1.085, 1.03)
        z = z0 + (z1 - z0) * ease(t / D)
        for c in self.cues_cache():
            dt = t - c
            if 0 <= dt < 0.5: z += 0.018 * math.sin(math.pi * dt / 0.5) * (1 - dt / 0.5)
        ang = (i * 2.399) % (2 * math.pi)
        px = math.cos(ang) * (z - 1) * W * 0.32 * (t / D - 0.5)
        py = math.sin(ang) * (z - 1) * H * 0.32 * (t / D - 0.5)
        M = np.float32([[z, 0, (1 - z) * W / 2 + px], [0, z, (1 - z) * H / 2 + py]])
        return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    def cues_cache(self):
        if not hasattr(self, "_cc"): self._cc = self.all_cues()
        return self._cc

    def transition(self, img, t):
        kind = self.spec.get("transition", "zoom"); T = 0.42
        if t >= T or kind == "cut": return img
        k = ease_out(t / T)
        if kind == "zoom":
            z = 1.18 - 0.18 * k
            M = np.float32([[z, 0, (1 - z) * W / 2], [0, z, (1 - z) * H / 2]])
            img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
            return cv2.addWeighted(img, k, np.zeros_like(img), 0, 0) if k < 1 else img
        if kind == "slide":
            off = int(W * 0.35 * (1 - k)); out = bg_base(self.theme).copy()
            out[:, off:] = img[:, :W - off] if off > 0 else img
            return out
        if kind == "wipe":
            x = int(-300 + (W + 600) * k); out = img.copy()
            bg = np.full_like(img, self.th["bg1"])
            if x < W: out[:, max(0, x):] = bg[:, max(0, x):]
            pts = np.int32([[x - 60, 0], [x + 140, 0], [x + 40, H], [x - 160, H]])
            cv2.fillConvexPoly(out, pts, self.acc, cv2.LINE_AA)
            pts2 = np.int32([[x + 150, 0], [x + 190, 0], [x + 90, H], [x + 50, H]])
            cv2.fillConvexPoly(out, pts2, self.acc2, cv2.LINE_AA)
            return out
        if kind == "flash":
            a = 1 - ease(t / 0.3)
            z = 1.07 - 0.07 * k
            M = np.float32([[z, 0, (1 - z) * W / 2], [0, z, (1 - z) * H / 2]])
            img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
            if a > 0: img = cv2.addWeighted(img, 1 - a * 0.85, np.full_like(img, 255), a * 0.85, 0)
            return img
        return img

    # ---------- captions
    def caption_chunks(self):
        if hasattr(self, "_chunks"): return self._chunks
        size = 52; chunks, cur = [], []
        for w in self.words:
            cur.append(w)
            line = " ".join(x["w"] for x in cur)
            end = w["w"][-1] in ".?!" or (w["w"][-1] in ",;:" and len(cur) >= 3) or len(cur) >= 6 or tw(line, size, "ExtraBold") > 1250
            if end: chunks.append(cur); cur = []
        if cur: chunks.append(cur)
        # avoid 1-word orphans
        merged = []
        for c in chunks:
            if merged and len(c) == 1 and len(merged[-1]) < 6 and merged[-1][-1]["w"][-1] not in ".?!": merged[-1] += c
            else: merged.append(c)
        self._chunks = merged; return merged

    def captions(self, img, t):
        size = 52; chunks = self.caption_chunks()
        for i, ch in enumerate(chunks):
            st = ch[0]["s"] - 0.08
            en = chunks[i + 1][0]["s"] - 0.08 if i + 1 < len(chunks) else ch[-1]["e"] + 0.7
            en = min(en, ch[-1]["e"] + 1.2)
            if not (st <= t < en): continue
            sw = tw(" ", size, "ExtraBold")
            widths = [tw(w["w"], size, "ExtraBold") for w in ch]
            total = sum(widths) + sw * (len(ch) - 1)
            cy = H - 112; x = W / 2 - total / 2
            a = fade(t, st, st + 0.12)
            panel(img, x - 30, cy - 46, x + total + 30, cy + 46, 22, (5, 8, 16, 190), alpha=a)
            for w, ww in zip(ch, widths):
                spoken = t >= w["s"] - 0.04
                current = spoken and t < max(w["e"], w["s"] + 0.15)
                col = self.acc if current else WHITE
                txt(img, w["w"], x, cy, size, "ExtraBold", col, a * (1.0 if spoken else 0.32), "lm")
                x += ww + sw
            break

    def chrome(self, img, t):
        job = self.job; tg = job["t0"] + t; total = job["total"]
        img[0:7, :] = (img[0:7, :] * 0.45).astype(np.uint8)
        x = int(W * tg / total); img[0:7, :x] = self.acc
        for c in job["chapter_starts"]:
            cx = int(W * c / total); img[0:7, max(0, cx - 2):cx + 2] = (240, 240, 240)
        lab = job.get("chapter_label")
        if lab:
            pill(img, lab, 34, 52, 24, mix(self.acc, (0, 0, 0), 0.3), alpha=0.92, anchor="l", weight="SemiBold", dot=self.acc)


# ---------------------------------------------------------------- templates
def T_hook_title(S, img, t):
    d = S.d
    for k in range(5):
        r = int(((t * 0.35 + k / 5) % 1.0) * 1100)
        cv2_alpha(img, 0.5 * (1 - r / 1100), lambda o, r=r: cv2.circle(o, (W // 2, H // 2), r, S.acc, 2, cv2.LINE_AA))
    a = fade(t, 0.0, 0.3)
    txt(img, d.get("kicker", ""), W / 2, 200, 34, "Bold", S.acc, a)
    lines = d["lines"]; sizes = []
    for ln in lines:
        sizes.append(fit(ln["text"], 190 if ln.get("accent") else 112, 1600, "Black"))
    hs = [s * 1.12 for s in sizes]; y = 520 - sum(hs) / 2
    for ln, s, h in zip(lines, sizes, hs):
        al, sc = pop(t - S.cue(ln.get("cue"), 0))
        col = S.acc if ln.get("accent") else WHITE
        txt(img, ln["text"], W / 2, y + h / 2, s, "Black", col, al, "mm", sc, glow=S.acc if ln.get("accent") else None)
        y += h
    st = d.get("stamp")
    if st:
        al, sc = pop(t - S.cue(st["cue"]))
        pill(img, st["text"], W / 2, 815, 46, S.acc2, alpha=al, scale=sc, dot=S.acc2)

def T_globe(S, img, t):
    d = S.d; pin = d.get("pin")
    lon0 = (pin["lon"] - 30 + 3.5 * t) if pin else (-40 + 7 * t)
    pa = fade(t, S.cue(pin["cue"]), S.cue(pin["cue"]) + 0.3) if pin else 0
    ra = fade(t, S.cue(d["rays"]["cue"]), S.cue(d["rays"]["cue"]) + 0.8) if d.get("rays") else 0
    globe_frame(img, 620, 520, 290, lon0, 18, S.theme, t, d.get("satellites", True), d.get("planes", 6),
                (pin["lat"], pin["lon"]) if pin else None, pa, ra)
    labels = d.get("labels", []); n = len(labels)
    y0 = 520 - (n - 1) * 135 / 2
    for i, lb in enumerate(labels):
        dt = t - S.cue(lb["cue"]); al = ease(dt / 0.25) if dt >= 0 else 0
        off = 120 * (1 - ease_out(dt / 0.4)) if dt >= 0 else 0
        pill(img, lb["text"], 1190 + off, y0 + i * 135, 50, S.acc, alpha=al, anchor="l", dot=S.acc2, max_w=560)

def T_question(S, img, t):
    d = S.d
    a0, s0 = pop(t - 0.15, 0.5)
    bob = 1 + 0.03 * math.sin(t * 2.2)
    txt(img, "?", 1450, 520 + 12 * math.sin(t * 1.6), 620, "Black", S.acc, a0, "mm", s0 * bob, glow=S.acc)
    txt(img, d.get("kicker", ""), 170, 290, 36, "Bold", S.acc2, fade(t, 0, .3), "lm")
    size, lines = fit_wrap(d["text"], 96, 1020, 4, "Black")
    tc = S.cue(d.get("cue"), 0.3); words_total = sum(len(l.split()) for l in lines); shown = 0
    y = 380; lh = size * 1.15
    for ln in lines:
        x = 170
        for w in ln.split():
            dt = t - (tc + shown * 0.09); al = ease(dt / 0.15) if dt >= 0 else 0
            ww = txt(img, w, x, y + lh / 2 + (1 - al) * 20, size, "Black", WHITE, al, "lm")
            x += tw(w + " ", size, "Black"); shown += 1
        y += lh
    sb = d.get("sub")
    if sb:
        al, sc = pop(t - S.cue(sb["cue"]))
        pill(img, sb["text"], 170, y + 70, 40, S.acc2, alpha=al, anchor="l", dot=S.acc2, max_w=980)

def side_visual(S, img, t, kind, cx, cy):
    if kind == "satellite":
        for k in range(4):
            r = ((t * 0.6 + k / 4) % 1.0)
            cv2_alpha(img, 0.7 * (1 - r), lambda o, r=r: cv2.ellipse(o, (cx, cy + 40), (int(40 + 260 * r), int(40 + 260 * r)), 0, 30, 150, S.acc, 4, cv2.LINE_AA),
                      (cx - 320, cy - 300, cx + 320, cy + 360))
        satellite(img, cx, cy - 40 + 10 * math.sin(t * 1.5), 2.0, S.acc, ang=8 * math.sin(t * 0.7))
    elif kind == "signal":
        sx, sy, px, py = cx - 120, cy - 230, cx + 120, cy + 200
        satellite(img, sx, sy, 1.0, S.acc, 15)
        phone(img, px, py, 1.0, dot=S.acc2)
        for k in range(3):
            r = (t * 0.9 + k / 3) % 1.0
            x = int(sx + (px - sx) * r); y = int(sy + (py - sy) * r)
            cv2.circle(img, (x, y), 12, S.acc2, -1, cv2.LINE_AA)
        cv2_alpha(img, 0.4, lambda o: cv2.line(o, (sx, sy), (px, py), S.acc2, 2, cv2.LINE_AA))
    elif kind == "clock":
        clock(img, cx, cy, 210, t * 2.6, S.acc, None)
    elif kind == "progress":
        panel(img, cx - 260, cy - 120, cx + 260, cy + 120, 26, (8, 12, 22, 220), S.acc + (255,), 3)
        txt(img, "Downloading almanac…", cx - 220, cy - 50, 34, "SemiBold", WHITE, 1, "lm")
        p = clamp(t / 60.0) * 0.9 + 0.02
        panel(img, cx - 220, cy + 10, cx + 220, cy + 46, 18, (40, 46, 60, 255))
        panel(img, cx - 220, cy + 10, cx - 220 + max(36, 440 * p), cy + 46, 18, S.acc + (255,))
        secs = int(750 - t * 1.0)
        txt(img, f"{secs // 60}:{secs % 60:02d} remaining", cx - 220, cy + 85, 30, "Medium", MUTE, 1, "lm")

def clock(img, cx, cy, R, ang, col, ghost=None):
    cv2.circle(img, (cx, cy), R + 14, mix(col, (0, 0, 0), 0.75), -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), R, (16, 22, 38), -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), R, col, 6, cv2.LINE_AA)
    for k in range(60):
        a = k * math.pi / 30; l = R * (0.13 if k % 5 == 0 else 0.05)
        p1 = (int(cx + (R - 18) * math.cos(a)), int(cy + (R - 18) * math.sin(a)))
        p2 = (int(cx + (R - 18 - l) * math.cos(a)), int(cy + (R - 18 - l) * math.sin(a)))
        cv2.line(img, p1, p2, MUTE, 3 if k % 5 == 0 else 2, cv2.LINE_AA)
    if ghost is not None:
        g = -math.pi / 2 + ghost
        cv2.line(img, (cx, cy), (int(cx + R * 0.8 * math.cos(g)), int(cy + R * 0.8 * math.sin(g))), (200, 205, 220), 5, cv2.LINE_AA)
    a = -math.pi / 2 + ang
    cv2.line(img, (cx, cy), (int(cx + R * 0.82 * math.cos(a)), int(cy + R * 0.82 * math.sin(a))), col, 7, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), 14, col, -1, cv2.LINE_AA)

def T_big_number(S, img, t):
    d = S.d; side = d.get("side")
    cx = 1250 if side else W / 2
    if side: side_visual(S, img, t, side, 470, 470)
    tc = S.cue(d.get("cue"), 0.3); k = ease_out((t - tc) / 1.1) if t >= tc else 0
    v = d["value"] * k; dec = d.get("decimals", 0)
    s = f"{d.get('prefix', '')}{v:,.{dec}f}{d.get('suffix', '')}"
    full = f"{d.get('prefix', '')}{d['value']:,.{dec}f}{d.get('suffix', '')}"
    size = fit(full, 300, 980 if side else 1500, "Black")
    al, sc = pop(t - tc, 0.5)
    ny = 360 if len(d.get("subs", [])) > 2 else 390
    txt(img, s, cx, ny, size, "Black", S.acc, al, "mm", sc, glow=S.acc)
    ls = fit(d.get("label", ""), 56, 980 if side else 1500, "SemiBold")
    txt(img, d.get("label", ""), cx, ny + size * 0.62 + 30, ls, "SemiBold", WHITE, fade(t, tc + 0.3, tc + 0.6))
    y = ny + size * 0.62 + 130
    for sb in d.get("subs", []):
        al, sc = pop(t - S.cue(sb["cue"]))
        pill(img, sb["text"], cx, y, 40, S.acc2, alpha=al, scale=sc, dot=S.acc2, max_w=900)
        y += 84

def T_versus(S, img, t):
    d = S.d; hd = d.get("header")
    top = 250 if hd else 200; bot = 790
    if hd:
        al, sc = pop(t - S.cue(hd["cue"]))
        txt(img, hd["text"], W / 2, 165, 58, "Bold", WHITE, al, "mm", sc, max_w=1600)
    for side, x0, x1, col in (("left", 150, 880, (210, 215, 230)), ("right", 1040, 1770, S.acc)):
        c = d[side]; dt = t - S.cue(c["cue"])
        if dt < 0:
            panel(img, x0, top, x1, bot, 30, (255, 255, 255, 12), (255, 255, 255, 38), 2, fade(t, 0, 0.4)); continue
        k = ease_out(dt / 0.45); off = (1 - k) * (-260 if side == "left" else 260)
        a = ease(dt / 0.25); x0o, x1o = x0 + off, x1 + off; cx = (x0o + x1o) / 2; ww = x1 - x0 - 80
        panel(img, x0o, top, x1o, bot, 30, (10, 14, 26, 225), col + (255,), 4, a)
        txt(img, c["title"], cx, top + 75, 44, "SemiBold", col, a, max_w=ww)
        vs = fit(c["value"], 150, ww, "Black")
        txt(img, c["value"], cx, top + 240, vs, "Black", WHITE, a, glow=col if side == "right" else None)
        us, ul = fit_wrap(c.get("unit", ""), 40, ww, 2, "Medium")
        for i, l in enumerate(ul): txt(img, l, cx, top + 360 + i * us * 1.2, us, "Medium", MUTE, a)
        if "bar" in c:
            by = bot - 80; bx0, bx1 = x0o + 40, x1o - 40
            panel(img, bx0, by, bx1, by + 32, 16, (40, 46, 62, 255), alpha=a)
            p = c["bar"] * ease_out((dt - 0.3) / 0.9)
            if p > 0: panel(img, bx0, by, bx0 + max(32, (bx1 - bx0) * p), by + 32, 16, col + (255,), alpha=a)
    bd = d.get("badge")
    if bd:
        al, sc = pop(t - S.cue(bd["cue"]))
        if al > 0 and len(bd["text"]) > 3:
            pill(img, bd["text"], W / 2, 520, 50, (14, 16, 24), fg=(14, 16, 24), alpha=al, scale=sc, fill=S.acc2 + (255,), weight="Black")
        elif al > 0:
            r = int(92 * sc)
            cv2_alpha(img, al, lambda o: (cv2.circle(o, (W // 2, 520), r + 8, (10, 14, 26), -1, cv2.LINE_AA), cv2.circle(o, (W // 2, 520), r, S.acc2, -1, cv2.LINE_AA)))
            txt(img, bd["text"], W / 2, 520, fit(bd["text"], 52, 150 * sc, "Black"), "Black", (14, 16, 24), al, "mm", sc)
    ft = d.get("footer")
    if ft:
        al, sc = pop(t - S.cue(ft["cue"]))
        txt(img, ft["text"], W / 2, 845, 46, "Bold", S.acc2, al, "mm", sc, max_w=1500)

def T_broadcast(S, img, t):
    d = S.d; sx, sy = 360, 330
    for k in range(5):
        r = (t * 0.5 + k / 5) % 1.0
        cv2_alpha(img, 0.8 * (1 - r), lambda o, r=r: cv2.circle(o, (sx, sy), int(60 + 700 * r), S.acc, 3, cv2.LINE_AA))
    satellite(img, sx, sy + 8 * math.sin(t * 1.4), 1.7, S.acc, ang=10)
    phone(img, 360, 760, 1.0, dot=S.acc2)
    x0, y0, x1, y1 = 700, 270, 1770, 800
    bc = S.cue(d.get("box_cue"), 0.15); a = fade(t, bc, bc + 0.35)
    panel(img, x0, y0, x1, y1, 26, (6, 10, 20, 235), S.acc + (255,), 3, a)
    panel(img, x0, y0, x1, y0 + 74, 26, mix(S.acc, (0, 0, 0), 0.6) + (255,), alpha=a)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cv2_alpha(img, a, lambda o, i=i, c=c: cv2.circle(o, (x0 + 38 + i * 34, y0 + 37), 10, c, -1, cv2.LINE_AA))
    txt(img, d.get("title", ""), x0 + 150, y0 + 37, 30, "Bold", WHITE, a, "lm", mono=True, max_w=880)
    y = y0 + 150
    for ln in d["lines"]:
        tc = S.cue(ln["cue"]); n = int(max(0, t - tc) * 40)
        s = ln["text"]
        if ln.get("ticking") and n >= len(s):
            ms = int(((t - tc) * 1e6) % 1e9); s = s[:s.index(":") + 2] + f"12:00:{7 + int(t - tc):02d}.{ms:09d}"
        part = s[:n]
        col = {"accent": S.acc, "accent2": S.acc2}.get(ln.get("color"), WHITE)
        size = fit(ln["text"] + "0000", 44, x1 - x0 - 90, "Bold", True)
        if part:
            txt(img, part, x0 + 50, y, size, "Bold", col, 1, "lm", mono=True)
            if n < len(s) or int(t * 2) % 2 == 0:
                cx = x0 + 50 + tw(part, size, "Bold", True) + 6
                cv2.rectangle(img, (int(cx), int(y - size * 0.45)), (int(cx + size * 0.5), int(y + size * 0.45)), col, -1)
        y += 140

def T_flow(S, img, t):
    d = S.d; steps = d["steps"]; n = len(steps); gap = 100
    x0, x1 = 150, 1770; bw = (x1 - x0 - gap * (n - 1)) / n; cy = 560 if d.get("header") else 520; bh = 260
    hd = d.get("header")
    if hd:
        al, sc = pop(t - S.cue(hd["cue"]))
        pill(img, hd["text"], W / 2, 250, 54, S.acc, alpha=al, scale=sc, dot=S.acc2)
    h2 = d.get("header2")
    if h2:
        al, sc = pop(t - S.cue(h2["cue"]))
        txt(img, h2["text"], W / 2, 345, 64, "Black", WHITE, al, "mm", sc, max_w=1500)
    times = [S.cue(s["cue"]) for s in steps]
    latest = max([i for i, tc in enumerate(times) if t >= tc], default=-1)
    for i, s in enumerate(steps):
        bx = x0 + i * (bw + gap); dt = t - times[i]
        if i > 0 and dt > -0.35:
            p = ease_out((dt + 0.35) / 0.35); ax0 = bx - gap + 12; ax1 = ax0 + (gap - 24) * p
            cv2.line(img, (int(ax0), cy), (int(ax1), cy), S.acc2, 6, cv2.LINE_AA)
            if p > 0.95:
                cv2.fillConvexPoly(img, np.int32([[ax1 + 4, cy], [ax1 - 18, cy - 16], [ax1 - 18, cy + 16]]), S.acc2, cv2.LINE_AA)
        if dt < 0:
            panel(img, bx, cy - bh / 2, bx + bw, cy + bh / 2, 28, (255, 255, 255, 12), (255, 255, 255, 38), 2, fade(t, 0, 0.4)); continue
        al, sc = pop(dt)
        active = i == latest; col = S.acc if active else mix(S.acc, (120, 130, 150), 0.6)
        w2, h2 = bw * sc, bh * sc; cx = bx + bw / 2
        if active:
            blit(img, glow_sprite(260, S.acc), int(cx - 260), int(cy - 260), 0.25)
        panel(img, cx - w2 / 2, cy - h2 / 2, cx + w2 / 2, cy + h2 / 2, 28, (10, 14, 26, 235), col + (255,), 4 if active else 3, al)
        size, lines = fit_wrap(s["text"], 56, bw - 50, 2, "Bold")
        sub = s.get("sub", ""); ssz, sl = fit_wrap(sub, 36, bw - 50, 2, "Medium")
        tot = len(lines) * size * 1.15 + (len(sl) * ssz * 1.25 + 14 if sub else 0)
        y = cy - tot / 2
        for l in lines: txt(img, l, cx, y + size * 0.58, size, "Bold", WHITE, al, "mm", sc); y += size * 1.15
        y += 14
        for l in sl: txt(img, l, cx, y + ssz * 0.6, ssz, "Medium", S.acc2 if active else MUTE, al, "mm", sc); y += ssz * 1.25
        txt(img, f"{i + 1:02d}", bx + 30, cy - bh / 2 - 34, 34, "Black", col, al, "lm")

CIRC_SATS = [(560, 500), (1330, 470), (1560, 790)]
CIRC_YOU = (930, 300)
CIRC_COL = lambda S: [S.acc, S.acc2, (180, 130, 255)]
def T_circles(S, img, t):
    d = S.d; cols = CIRC_COL(S)
    stages = [(S.cue(s["cue"]), s) for s in d["stages"]]
    n = 0; pts = False; you = False; tn = [None, None, None]
    if d.get("instant_first"): n = 1; tn[0] = -9.0
    for tc, s in stages:
        if t >= tc:
            for k in range(n, s["n"]): tn[k] = tc
            n = max(n, s["n"]); pts = pts or s.get("points", False); you = you or s.get("you", False)
    if S.spec.get("continues"): pass
    for i in range(3):
        c = CIRC_SATS[i]; r = math.dist(c, CIRC_YOU)
        if i < n:
            dt = t - tn[i]
            if i == 0 and stages and stages[0][0] == tn[0] and S.idx > 0 and d.get("instant_first"): dt = 9
            p = ease_out(dt / 1.1)
            cv2_alpha(img, 0.10 * p, lambda o, c=c, r=r, i=i: cv2.circle(o, c, int(r), cols[i], -1, cv2.LINE_AA))
            cv2.ellipse(img, c, (int(r), int(r)), -90, 0, 360 * p, cols[i], 5, cv2.LINE_AA)
            satellite(img, c[0], c[1], 0.85, cols[i], ang=15)
            if p < 1:
                a = math.radians(-90 + 360 * p)
                cv2.line(img, c, (int(c[0] + r * math.cos(a)), int(c[1] + r * math.sin(a))), cols[i], 2, cv2.LINE_AA)
        else:
            satellite(img, c[0], c[1], 0.85, mix(cols[i], (40, 50, 70), 0.75), ang=15)
    if n == 1 and not you:
        a = 0.75 + 0.45 * math.sin(t * 0.6); c = CIRC_SATS[0]; r = math.dist(c, CIRC_YOU)
        px, py = c[0] + r * math.cos(a), c[1] + r * math.sin(a)
        if t > (tn[0] or 0) + 1.0:
            phone(img, px, py, 0.55, dot=S.acc2); txt(img, "?", px + 45, py - 60, 64, "Black", S.acc2)
    if pts:
        (x1, y1), (x2, y2) = CIRC_SATS[0], CIRC_SATS[1]
        r1, r2 = math.dist(CIRC_SATS[0], CIRC_YOU), math.dist(CIRC_SATS[1], CIRC_YOU)
        dd = math.dist(CIRC_SATS[0], CIRC_SATS[1]); a = (r1 ** 2 - r2 ** 2 + dd ** 2) / (2 * dd); h = math.sqrt(max(0, r1 ** 2 - a ** 2))
        mx, my = x1 + a * (x2 - x1) / dd, y1 + a * (y2 - y1) / dd
        for sg in (1, -1):
            px, py = mx + sg * h * (y2 - y1) / dd, my - sg * h * (x2 - x1) / dd
            if you and math.dist((px, py), CIRC_YOU) > 5:
                cv2.drawMarker(img, (int(px), int(py)), (150, 150, 160), cv2.MARKER_TILTED_CROSS, 40, 5, cv2.LINE_AA); continue
            cv2.circle(img, (int(px), int(py)), int(14 + 4 * math.sin(t * 8)), WHITE, -1, cv2.LINE_AA)
    if you:
        tc = [tc for tc, s in stages if s.get("you")][0]
        map_pin(img, *CIRC_YOU, 1.4, S.acc2, t)
        al, sc = pop(t - tc)
        txt(img, "YOU", CIRC_YOU[0] + 70, CIRC_YOU[1] - 10, 78, "Black", WHITE, al, "lm", sc, glow=S.acc2)
    ct = d.get("caption_top")
    if ct:
        al, sc = pop(t - S.cue(ct["cue"]))
        pill(img, ct["text"], W / 2, 150, 44, S.acc, alpha=al, scale=sc)
    txt(img, "2D VIEW", W - 170, 150, 28, "Bold", MUTE, 0.8, "rm")

def T_tiles(S, img, t):
    d = S.d; items = d["items"]; n = len(items); gap = 40
    x0, x1 = 150, 1770; w = (x1 - x0 - gap * (n - 1)) / n; y0, y1 = 360, 760
    ti = d.get("title")
    if ti:
        al, sc = pop(t - S.cue(ti["cue"]))
        txt(img, ti["text"], W / 2, 230, 88, "Black", WHITE, al, "mm", sc, glow=S.acc, max_w=1600)
    for i, it in enumerate(items):
        dt = t - S.cue(it["cue"])
        if dt < 0:
            panel(img, x0 + i * (w + gap), y0, x0 + i * (w + gap) + w, y1, 30, (255, 255, 255, 14), (255, 255, 255, 40), 2)
            continue
        al = ease(dt / 0.2); off = 80 * (1 - ease_out(dt / 0.45))
        col = S.acc2 if it.get("accent") else S.acc
        bx = x0 + i * (w + gap); cx = bx + w / 2
        panel(img, bx, y0 + off, bx + w, y1 + off, 30, (10, 14, 26, 235), col + (255,), 4, al)
        sub = it.get("sub", "")
        if len(sub) <= 2:
            txt(img, sub, cx, y0 + 140 + off, 150, "Black", col, al, glow=col)
            txt(img, it["text"], cx, y1 - 100 + off, fit(it["text"], 60, w - 50, "Black"), "Black", WHITE, al)
        else:
            txt(img, it["text"], cx, (y0 + y1) / 2 - 40 + off, fit(it["text"], 72, w - 50, "Black"), "Black", col, al, glow=col)
            ss, sl = fit_wrap(sub, 40, w - 60, 2, "Medium")
            for k, l in enumerate(sl): txt(img, l, cx, (y0 + y1) / 2 + 50 + k * ss * 1.25 + off, ss, "Medium", WHITE, al)
    fts = d.get("footers") or ([d["footer"]] if d.get("footer") else [])
    cur = [f for f in fts if t >= S.cue(f["cue"])]
    if cur:
        ft = cur[-1]; al, sc = pop(t - S.cue(ft["cue"]))
        pill(img, ft["text"], W / 2, 835, 44, S.acc2, alpha=al, scale=sc, dot=S.acc2)

def T_top_list(S, img, t):
    d = S.d; items = d["items"]; n = len(items); rh = 128
    ti = d.get("title")
    if ti:
        al, sc = pop(t - S.cue(ti["cue"]))
        txt(img, ti["text"], W / 2, 200, 84, "Black", WHITE, al, "mm", sc, glow=S.acc, max_w=1600)
    bd = d.get("badge")
    if bd:
        al, sc = pop(t - S.cue(bd["cue"]))
        pill(img, bd["text"], W / 2, 300, 40, S.acc2, alpha=al, scale=sc, dot=S.acc2)
    ft = d.get("footer")
    y0 = 560 - (n - 1) * rh / 2 + (60 if bd else 20) - (45 if ft else 0)
    if ft:
        al, sc = pop(t - S.cue(ft["cue"]))
        pill(img, ft["text"], W / 2, y0 + n * rh + 10, 42, S.acc2, alpha=al, scale=sc, dot=S.acc2)
    for i, it in enumerate(items):
        dt = t - S.cue(it["cue"])
        if dt < 0: continue
        al = ease(dt / 0.2); off = -200 * (1 - ease_out(dt / 0.45)); y = y0 + i * rh
        x0, x1 = 330 + off, 1590 + off
        panel(img, x0, y - 52, x1, y + 52, 26, (10, 14, 26, 230), S.acc + (180,), 3, al)
        cv2_alpha(img, al, lambda o: cv2.circle(o, (int(x0 + 60), int(y)), 34, S.acc, -1, cv2.LINE_AA), (x0, y - 60, x0 + 120, y + 60))
        txt(img, str(i + 1), x0 + 60, y, 40, "Black", (10, 14, 26), al)
        txt(img, it["text"], x0 + 125, y, 58, "Black", WHITE, al, "lm", max_w=640)
        txt(img, it.get("sub", ""), x1 - 40, y, 40, "Medium", S.acc2, al, "rm", max_w=500)

def T_quote(S, img, t):
    d = S.d
    txt(img, "“", 250, 330, 360, "Black", mix(S.th["bg2"], S.acc, 0.22), fade(t, 0, .4))
    kk = d.get("kicker")
    if kk: pill(img, kk, W / 2, 210, 38, S.acc, alpha=fade(t, 0.05, 0.35), dot=S.acc)
    pre = d.get("pre")
    if pre:
        al, sc = pop(t - S.cue(pre["cue"]))
        txt(img, pre["text"], W / 2, 330, 60, "Bold", MUTE, al, "mm", sc)
    mono = d.get("mono", False)
    size, lines = fit_wrap(d["text"], 150 if mono else 100, 1560, 1 if mono else 3, "ExtraBold" if mono else "Black", mono)
    tc = S.cue(d.get("cue"), 0.3); lh = size * 1.18
    yc = 480 if (d.get("source") and d.get("stamp")) else 520
    y = yc - (len(lines) - 1) * lh / 2; k = 0
    for ln in lines:
        words = ln.split(); lw = tw(ln, size, "Black", mono); x = W / 2 - lw / 2
        for w in words:
            dt = t - (tc + k * 0.14); al = ease(dt / 0.15) if dt >= 0 else 0
            txt(img, w, x, y + (1 - al) * 18, size, "Black", S.acc if mono else WHITE, al, "lm", mono=mono, glow=S.acc if mono else None)
            x += tw(w + " ", size, "Black", mono); k += 1
        y += lh
    src = d.get("source")
    if src:
        al, sc = pop(t - S.cue(src["cue"]))
        txt(img, "— " + src["text"], W / 2, y + 20, 50, "SemiBold", S.acc2, al, "mm", sc, max_w=1500)
        y += 60
    st = d.get("stamp")
    if st:
        al, sc = pop(t - S.cue(st["cue"]))
        pill(img, st["text"], W / 2, min(825, max(y + 60, 760)), 42, S.acc2, alpha=al, scale=sc, dot=S.acc2)

def T_timeline(S, img, t):
    d = S.d; ev = d["events"]; gap = 560; ly = 540
    times = [S.cue(e["cue"]) for e in ev]
    cur = max([i for i, tc in enumerate(times) if t >= tc], default=d.get("start_index", 0))
    prev = max([i for i, tc in enumerate(times) if t >= tc + 0.0 and i < cur], default=cur)
    k = ease((t - times[cur]) / 0.8) if cur < len(times) else 1
    focus = prev + (cur - prev) * k
    camx = W / 2 - 300 - focus * gap + min(focus, 1) * 0
    xs = [camx + 300 + i * gap for i in range(len(ev))]
    notes = [(S.cue(nt["cue"]), nt) for nt in d.get("notes", [])]
    curn = [nt for tc, nt in notes if t >= tc]
    if curn:
        nt = curn[-1]; al, sc = pop(t - S.cue(nt["cue"]))
        pill(img, nt["text"], W / 2, 200, 48, S.acc, alpha=al, scale=sc, dot=S.acc2)
    end_x = xs[cur] if t >= times[cur] else xs[0]
    cv2.line(img, (0, ly), (W, ly), mix(S.th["bg2"], (255, 255, 255), 0.15), 4, cv2.LINE_AA)
    cv2.line(img, (0, ly), (int(min(W, end_x)), ly), S.acc, 6, cv2.LINE_AA)
    for i, e in enumerate(ev):
        x = xs[i]
        if x < -400 or x > W + 400: continue
        dt = t - times[i]
        if dt < 0:
            cv2.circle(img, (int(x), ly), 14, mix(S.th["bg2"], (255, 255, 255), 0.25), -1, cv2.LINE_AA); continue
        al, sc = pop(dt)
        cv2.circle(img, (int(x), ly), int(24 * sc), S.acc, -1, cv2.LINE_AA)
        cv2.circle(img, (int(x), ly), int(11 * sc), WHITE, -1, cv2.LINE_AA)
        txt(img, e["year"], x, ly - 120, 120, "Black", S.acc if i == cur else WHITE, al, "mm", sc, glow=S.acc if i == cur else None)
        ss, sl = fit_wrap(e["text"], 46, 470, 3, "SemiBold")
        for j, l in enumerate(sl): txt(img, l, x, ly + 80 + j * ss * 1.25, ss, "SemiBold", WHITE if i == cur else MUTE, al)

def T_chart(S, img, t):
    d = S.d; pts = d["points"]; x0, x1, y0, y1 = 300, 1700, 290, 800
    txt(img, d.get("title", ""), W / 2, 175, 60, "Bold", WHITE, fade(t, 0, .3), max_w=1500)
    xmax = max(p[0] for p in pts); ymax = max(p[1] for p in pts)
    step = 20 if ymax <= 100 else 50; ytop = math.ceil(ymax / step) * step
    X = lambda v: x0 + (x1 - x0) * v / xmax; Y = lambda v: y1 - (y1 - y0) * v / ytop
    for v in range(0, int(ytop) + 1, step):
        cv2.line(img, (x0, int(Y(v))), (x1, int(Y(v))), mix(S.th["bg2"], (255, 255, 255), 0.12), 2, cv2.LINE_AA)
        txt(img, f"{v} {d.get('y_label', '')}", x0 - 24, Y(v), 30, "Medium", MUTE, 1, "rm")
    for p in pts: txt(img, f"Day {p[0]:g}", X(p[0]), y1 + 38, 30, "Medium", MUTE, 1)
    tc = S.cue(d.get("cue"), 0.3); dur = max(3.0, S.D - tc - 1.5)
    prog = clamp((t - tc) / dur) * xmax
    if prog > 0:
        xs = np.linspace(0, prog, 80); ys = np.interp(xs, [p[0] for p in pts], [p[1] for p in pts])
        poly = np.array([[X(a), Y(b)] for a, b in zip(xs, ys)])
        area = np.vstack([poly, [[X(prog), y1], [x0, y1]]])
        cv2_alpha(img, 0.22, lambda o: cv2.fillPoly(o, [np.int32(area * 4)], S.acc, cv2.LINE_AA, shift=2), (x0, y0 - 10, x1 + 10, y1))
        cv2.polylines(img, [np.int32(poly * 4)], False, S.acc, 7, cv2.LINE_AA, shift=2)
        hx, hy = poly[-1]
        cv2.circle(img, (int(hx), int(hy)), 14, WHITE, -1, cv2.LINE_AA)
        pill(img, f"{ys[-1]:.0f} km", hx, hy - 60, 36, S.acc, fill=(10, 14, 26, 230))
    for an in d.get("annotations", []):
        ta = max(S.cue(an["cue"]), tc + dur * an["x"] / xmax)
        al, sc = pop(t - ta)
        yv = np.interp(an["x"], [p[0] for p in pts], [p[1] for p in pts])
        if al > 0:
            cv2.circle(img, (int(X(an["x"])), int(Y(yv))), 12, S.acc2, -1, cv2.LINE_AA)
            pill(img, an["text"], X(an["x"]) + (130 if an["x"] < xmax else -90), Y(yv) + (45 if an["x"] < xmax else 95), 40, S.acc2, alpha=al, scale=sc)

def T_clock(S, img, t):
    d = S.d
    drift = 0.0 + max(0, t - 2.0) * 0.12
    clock(img, 520, 520, 270, t * 1.6 + drift, S.acc, ghost=t * 1.6)
    txt(img, "orbit", 430, 870, 34, "Bold", S.acc, 1, "rm"); txt(img, "ground", 610, 870, 34, "Bold", (210, 215, 230), 1, "lm")
    cv2.line(img, (445, 870), (480, 870), S.acc, 7, cv2.LINE_AA); cv2.line(img, (560, 870), (595, 870), (210, 215, 230), 5, cv2.LINE_AA)
    txt(img, d.get("kicker", ""), 930, 300, 36, "Bold", S.acc2, fade(t, 0, .3), "lm")
    y = 400
    for ln in d["lines"]:
        al, sc = pop(t - S.cue(ln["cue"]))
        size = fit(ln["text"], 92 if ln.get("accent") else 70, 840, "Black")
        txt(img, ln["text"], 930, y, size, "Black", S.acc if ln.get("accent") else WHITE, al, "lm", sc)
        y += size * 1.35

def T_noise(S, img, t):
    d = S.d; ti = d.get("title")
    if ti:
        al, sc = pop(t - S.cue(ti["cue"]))
        txt(img, ti["text"], W / 2, 190, 84, "Black", WHITE, al, "mm", sc, glow=S.acc)
    x0, x1, cy = 150, 1770, 530
    dig = S.cue(d.get("dig_cue"), S.D * 0.6); sigc = S.cue(d.get("signal_cue"), 0.5)
    na = 1 - 0.75 * fade(t, dig, dig + 1.5); sa = fade(t, sigc, sigc + 0.6)
    xs = np.arange(x0, x1, 3)
    rng = np.random.default_rng(int(t * 30))
    noise = rng.normal(0, 1, len(xs)) * 85 + np.sin(xs * 0.01 + t * 3) * 25
    pn = np.stack([xs, cy + noise], 1)
    cv2_alpha(img, 0.85 * na, lambda o: cv2.polylines(o, [np.int32(pn)], False, (150, 158, 178), 2, cv2.LINE_AA), (x0, cy - 330, x1, cy + 330))
    sig = np.sin(xs * 0.035 - t * 6) * 60 * sa
    ps = np.stack([xs, cy + sig], 1)
    boost = fade(t, dig, dig + 1.0)
    cv2.polylines(img, [np.int32(ps * 4)], False, mix(S.acc, (255, 255, 255), 0.2 * boost), int(3 + 4 * boost), cv2.LINE_AA, shift=2)
    if sa > 0: txt(img, "GPS signal", x1 - 10, cy - 300, 40, "Bold", S.acc, sa * (0.4 + 0.6 * boost), "rm")
    txt(img, "radio noise", x0 + 10, cy - 300, 36, "Bold", MUTE, na, "lm")
    lb = d.get("label"); l2 = d.get("label2")
    if l2 and t >= S.cue(l2["cue"]): lb = l2
    if lb:
        al, sc = pop(t - S.cue(lb["cue"]))
        pill(img, lb["text"], W / 2, 820, 44, S.acc2, alpha=al, scale=sc, dot=S.acc2)

def T_outro(S, img, t):
    d = S.d
    globe_frame(img, W // 2, 1250, 640, -20 + 4 * t, 10, S.theme, t, sats=False)
    al, sc = pop(t - S.cue(d.get("cue"), 0.3))
    size, lines = fit_wrap(d["text"], 96, 1600, 2, "Black")
    y = 250
    for l in lines: txt(img, l, W / 2, y, size, "Black", WHITE, al, "mm", sc, glow=S.acc); y += size * 1.15
    nx = d.get("next")
    if nx:
        dt = t - S.cue(nx["cue"]); al = ease(dt / 0.25) if dt >= 0 else 0; off = 60 * (1 - ease_out(dt / 0.5)) if dt >= 0 else 0
        x0, x1, y0, y1 = 410, 1510, 430 + off, 690 + off
        panel(img, x0, y0, x1, y1, 32, (8, 12, 22, 240), S.acc + (255,), 4, al)
        cv2_alpha(img, al, lambda o: cv2.fillConvexPoly(o, np.int32([[x0 + 80, y0 + 90], [x0 + 80, y0 + 170], [x0 + 150, y0 + 130]]), S.acc2, cv2.LINE_AA), (x0, y0, x0 + 200, y1))
        txt(img, "WATCH NEXT", x0 + 200, y0 + 70, 34, "Bold", S.acc2, al, "lm")
        ss, sl = fit_wrap(nx["text"], 56, x1 - x0 - 240, 2, "Black")
        for j, l in enumerate(sl): txt(img, l, x0 + 200, y0 + 135 + j * ss * 1.18, ss, "Black", WHITE, al, "lm")
    ct = d.get("cta")
    if ct:
        al, sc = pop(t - S.cue(ct["cue"]))
        pill(img, ct["text"], W / 2, 790, 44, S.acc2, alpha=al, scale=sc * (1 + 0.04 * math.sin(t * 6)), fill=S.acc2 + (255,), fg=(14, 16, 24), weight="Black")

TEMPLATES = {k[2:]: v for k, v in globals().items() if k.startswith("T_")}


# ---------------------------------------------------------------- rendering
def render_scene(job):
    S = Scene(job); n = job["frames"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-preset", job.get("preset", "medium"), "-crf", str(job.get("crf", 21)),
           "-maxrate", job.get("maxrate", "2M"), "-bufsize", job.get("bufsize", "4M"), "-g", "60",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-threads", "2", job["out"] + ".tmp.mp4"]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(np.ascontiguousarray(S.frame(i / FPS)).tobytes())
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError("ffmpeg failed for " + job["out"])
    os.replace(job["out"] + ".tmp.mp4", job["out"])
    return job["out"]

def still(job, t, path):
    S = Scene(job)
    Image.fromarray(S.frame(t)).save(path, quality=88)
