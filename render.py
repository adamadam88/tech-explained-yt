"""Sample tech-explainer renderer: "How does your phone know where you are?" (GPS).
Shapes with OpenCV (antialiased), text with PIL. One mp4 per scene, then concat."""
import math, os, subprocess, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
FD = "/usr/share/fonts/opentype/inter/"
def F(w, s): return ImageFont.truetype(FD + f"{'InterDisplay' if s>60 else 'Inter'}-{w}.otf", s)

BG = (12, 18, 32); BG2 = (20, 30, 52); CY = (64, 210, 255); OR = (255, 170, 60)
WH = (240, 244, 250); GR = (130, 145, 170); EARTH = (35, 95, 170); LAND = (60, 170, 120)

def ease(x): x = max(0, min(1, x)); return x * x * (3 - 2 * x)
def fade(t, a, b): return ease((t - a) / (b - a)) if b > a else float(t >= a)

def base():
    img = np.zeros((H, W, 3), np.uint8); img[:] = BG
    # subtle vertical gradient + grid
    g = np.linspace(0, 1, H)[:, None, None]
    img[:] = (np.array(BG) * (1 - g) + np.array(BG2) * g).astype(np.uint8)
    for x in range(0, W, 120): cv2.line(img, (x, 0), (x, H), (24, 34, 56), 1)
    for y in range(0, H, 120): cv2.line(img, (0, y), (W, y), (24, 34, 56), 1)
    return img

def blend(img, color, alpha, draw):
    if alpha <= 0: return
    ov = img.copy(); draw(ov, color)
    cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, dst=img)

def text(im, xy, s, font, fill=WH, alpha=1.0, anchor="la"):
    if alpha <= 0: return
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, s, font=font, fill=fill + (int(255 * alpha),), anchor=anchor)
    im.alpha_composite(layer)

def caption(im, s, t, start, end):
    """Burnt-in subtitle box at the bottom (stands in for narration)."""
    a = min(fade(t, start, start + .35), 1 - fade(t, end - .35, end))
    if a <= 0 or not s: return
    f = F("SemiBold", 44); d = ImageDraw.Draw(im)
    w = d.textlength(s, font=f); pad = 28
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(layer)
    x0, y0 = (W - w) / 2 - pad, H - 150
    dl.rounded_rectangle((x0, y0, x0 + w + 2 * pad, y0 + 84), 18, fill=(0, 0, 0, int(170 * a)))
    dl.text((W / 2, y0 + 42), s, font=f, fill=WH + (int(255 * a),), anchor="mm")
    im.alpha_composite(layer)

def captions(im, t, lines):
    for s, a, b in lines: caption(im, s, t, a, b)

def earth(img, c, r):
    cv2.circle(img, c, r + 18, (30, 60, 110), -1, cv2.LINE_AA)
    cv2.circle(img, c, r, EARTH, -1, cv2.LINE_AA)
    # stylised continents
    for dx, dy, rx, ry, ang in [(-.35, -.2, .32, .22, 20), (.3, .15, .25, .35, -15), (-.1, .45, .2, .12, 0), (.25, -.45, .2, .1, 10)]:
        cv2.ellipse(img, (int(c[0] + dx * r), int(c[1] + dy * r)), (int(rx * r), int(ry * r)), ang, 0, 360, LAND, -1, cv2.LINE_AA)
    mask = np.zeros(img.shape[:2], np.uint8); cv2.circle(mask, c, r, 255, -1)
    outside = mask == 0
    return outside

# ---------------- scenes ----------------
def s_title(t, D):
    img = base(); c = (W // 2, H // 2 + 40)
    for i in range(4):
        rr = int(180 + i * 120 + (t * 40) % 120)
        cv2.circle(img, c, rr, (30, 50, 85), 2, cv2.LINE_AA)
    im = Image.fromarray(img).convert("RGBA")
    a = fade(t, .2, .9); y = 380 - 30 * (1 - a)
    text(im, (W / 2, 300), "TECH, EXPLAINED", F("Bold", 34), CY, a, "mm")
    text(im, (W / 2, y + 90), "How does your phone", F("Black", 104), WH, a, "mm")
    a2 = fade(t, .6, 1.3)
    text(im, (W / 2, y + 220), "know where you are?", F("Black", 104), WH, a2, "mm")
    a3 = fade(t, 1.4, 2.0)
    text(im, (W / 2, 780), "GPS in 60 seconds", F("Medium", 44), GR, a3, "mm")
    return im

SATS = [(i * 2 * math.pi / 6, j * 2 * math.pi / 4 + i * .5) for i in range(6) for j in range(4)]
def s_orbit(t, D):
    img = base(); c = (W // 2 - 260, H // 2 - 30); R = 190
    zoom = 1 + .04 * t / D
    for k, (plane, _) in enumerate(SATS[::4]):
        cv2.ellipse(img, c, (int(400 * zoom), int(150 * zoom)), math.degrees(plane), 0, 360, (45, 70, 110), 2, cv2.LINE_AA)
    pts = []
    for plane, ph in SATS:
        a = ph + t * .35
        x, y = 400 * zoom * math.cos(a), 150 * zoom * math.sin(a)
        cp, sp = math.cos(plane), math.sin(plane)
        pts.append((int(c[0] + x * cp - y * sp), int(c[1] + x * sp + y * cp), math.sin(a)))
    for x, y, z in pts:
        if z < 0: cv2.circle(img, (x, y), 7, (90, 150, 190), -1, cv2.LINE_AA)
    earth(img, c, R)
    n = int(len(pts) * fade(t, .3, 3.5))
    for i, (x, y, z) in enumerate(pts):
        if z >= 0 and i < n + 24:
            cv2.circle(img, (x, y), 12, (20, 60, 90), -1, cv2.LINE_AA); cv2.circle(img, (x, y), 8, CY, -1, cv2.LINE_AA)
    im = Image.fromarray(img).convert("RGBA")
    a = fade(t, .5, 1.2)
    text(im, (1240, 330), "~31", F("Black", 170), CY, a)
    text(im, (1250, 520), "active GPS satellites", F("SemiBold", 42), WH, a)
    a2 = fade(t, 2.6, 3.3)
    text(im, (1240, 610), "20,200 km", F("Black", 110), OR, a2)
    text(im, (1250, 740), "above the Earth", F("SemiBold", 42), WH, a2)
    captions(im, t, [("Around 31 satellites circle the planet...", .3, 3.6), ("...each one about 20,200 km up.", 3.8, D - .2)])
    return im

def satellite(img, p, s=1.0, col=CY):
    x, y = p
    cv2.rectangle(img, (int(x - 70 * s), int(y - 14 * s)), (int(x - 26 * s), int(y + 14 * s)), (70, 110, 200), -1, cv2.LINE_AA)
    cv2.rectangle(img, (int(x + 26 * s), int(y - 14 * s)), (int(x + 70 * s), int(y + 14 * s)), (70, 110, 200), -1, cv2.LINE_AA)
    cv2.rectangle(img, (int(x - 22 * s), int(y - 22 * s)), (int(x + 22 * s), int(y + 22 * s)), col, -1, cv2.LINE_AA)

def phone(img, p):
    x, y = p
    cv2.rectangle(img, (x - 48, y - 90), (x + 48, y + 90), (200, 210, 225), -1, cv2.LINE_AA)
    cv2.rectangle(img, (x - 40, y - 78), (x + 40, y + 74), (15, 25, 45), -1, cv2.LINE_AA)
    cv2.circle(img, (x, y - 10), 14, OR, -1, cv2.LINE_AA)

def s_signal(t, D):
    img = base(); sp = (480, 280); pp = (1420, 780)
    for k in range(6):
        ph = (t * 1.1 - k * .45)
        if ph < 0: continue
        r = int((ph % 2.7) / 2.7 * 1300)
        al = max(0, 1 - r / 1300)
        blend(img, CY, .7 * al, lambda o, cc, r=r: cv2.circle(o, sp, r, cc, 3, cv2.LINE_AA))
    satellite(img, sp, 1.4); phone(img, pp)
    im = Image.fromarray(img).convert("RGBA")
    a = fade(t, 1.0, 1.6)
    box = Image.new("RGBA", im.size, (0, 0, 0, 0)); bd = ImageDraw.Draw(box)
    bd.rounded_rectangle((760, 200, 1380, 470), 24, fill=(10, 16, 30, int(230 * a)), outline=CY + (int(255 * a),), width=3)
    im.alpha_composite(box)
    mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 40)
    ms = int((t * 1000) % 1000)
    text(im, (800, 240), "SAT G-07  BROADCAST", mono, CY, a)
    text(im, (800, 315), "position: 26,560 km", mono, WH, a)
    text(im, (800, 390), f"time: 12:00:07.{ms:03d}", mono, OR, a)
    captions(im, t, [("Each satellite keeps broadcasting two things:", .2, 3.3), ("where it is, and exactly what time it is.", 3.5, D - .2)])
    return im

def s_trilat(t, D):
    img = base(); target = (1000, 560)
    circles = [((600, 380), 0), ((1420, 360), 1), ((1010, 900), 2)]
    cols = [CY, OR, (180, 120, 255)]
    for (c, i) in circles:
        r = int(math.dist(c, target)); a = fade(t, .6 + i * 1.6, 1.6 + i * 1.6)
        if a > 0:
            blend(img, cols[i], .12 * a, lambda o, cc, c=c, r=r: cv2.circle(o, c, r, cc, -1, cv2.LINE_AA))
            ang = 360 * a
            cv2.ellipse(img, c, (r, r), -90, 0, ang, cols[i], 4, cv2.LINE_AA)
        satellite(img, c, .8, cols[i])
    a = fade(t, 5.6, 6.2)
    if a > 0:
        pulse = 1 + .25 * math.sin(t * 6)
        blend(img, WH, a, lambda o, cc: cv2.circle(o, target, int(18 * pulse), cc, -1, cv2.LINE_AA))
        blend(img, OR, .5 * a, lambda o, cc: cv2.circle(o, target, int(40 * pulse), cc, 3, cv2.LINE_AA))
    im = Image.fromarray(img).convert("RGBA")
    text(im, (target[0] + 60, target[1] - 30), "YOU", F("Black", 64), WH, a)
    a2 = fade(t, .3, .9)
    text(im, (80, 70), "distance  =  speed of light  ×  travel time", F("Bold", 46), WH, a2)
    captions(im, t, [("Your phone times how long each signal took to arrive.", .3, 3.4),
                     ("One distance is a circle. Two narrow it down...", 3.6, 5.6),
                     ("...and where they all cross, that's you.", 5.8, D - .2)])
    return im

def s_clock(t, D):
    img = base(); c = (520, 520); R = 230
    cv2.circle(img, c, R, (30, 45, 75), -1, cv2.LINE_AA); cv2.circle(img, c, R, CY, 6, cv2.LINE_AA)
    for k in range(60):
        a = k * math.pi / 30; l = 30 if k % 5 == 0 else 12
        p1 = (int(c[0] + (R - 20) * math.cos(a)), int(c[1] + (R - 20) * math.sin(a)))
        p2 = (int(c[0] + (R - 20 - l) * math.cos(a)), int(c[1] + (R - 20 - l) * math.sin(a)))
        cv2.line(img, p1, p2, GR, 3, cv2.LINE_AA)
    ang = -math.pi / 2 + t * 2.4
    cv2.line(img, c, (int(c[0] + 190 * math.cos(ang)), int(c[1] + 190 * math.sin(ang))), OR, 6, cv2.LINE_AA)
    cv2.circle(img, c, 12, OR, -1, cv2.LINE_AA)
    im = Image.fromarray(img).convert("RGBA")
    a = fade(t, .4, 1.0); n = int(38 * fade(t, .4, 2.2))
    text(im, (900, 260), "Satellite clocks run fast by", F("SemiBold", 46), WH, a)
    text(im, (890, 330), f"{n} µs", F("Black", 220), CY, a)
    text(im, (900, 590), "every day — thanks to Einstein's relativity", F("SemiBold", 40), GR, a)
    a2 = fade(t, 4.2, 4.8)
    text(im, (900, 700), "Uncorrected, GPS would drift", F("SemiBold", 46), WH, a2)
    text(im, (900, 760), "~10 km a day.", F("Black", 90), OR, a2)
    captions(im, t, [("There's a catch: time runs differently up there.", .2, 4.0), ("So GPS corrects for relativity every single day.", 4.2, D - .2)])
    return im

def s_outro(t, D):
    img = base(); im = Image.fromarray(img).convert("RGBA")
    a = fade(t, .2, .8)
    text(im, (W / 2, 420), "Next time your map finds you,", F("Bold", 64), WH, a, "mm")
    text(im, (W / 2, 520), "thank Einstein.", F("Black", 96), CY, fade(t, .8, 1.4), "mm")
    a3 = fade(t, 2.0, 2.6)
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.rounded_rectangle((W / 2 - 230, 680, W / 2 + 230, 770), 45, fill=(230, 40, 50, int(255 * a3)))
    im.alpha_composite(lay)
    text(im, (W / 2, 725), "SUBSCRIBE", F("Black", 44), WH, a3, "mm")
    return im

SCENES = [("01_title", s_title, 4.0), ("02_orbit", s_orbit, 8.0), ("03_signal", s_signal, 7.5),
          ("04_trilat", s_trilat, 9.5), ("05_clock", s_clock, 8.5), ("06_outro", s_outro, 4.5)]

def with_fades(fn, D):
    def g(t):
        im = fn(t, D)
        k = min(fade(t, 0, .35), 1 - fade(t, D - .35, D))
        if k < 1:
            arr = np.asarray(im.convert("RGB")).astype(np.float32)
            bg = np.array(BG, np.float32)
            im = Image.fromarray((bg + (arr - bg) * k).astype(np.uint8))
        return im.convert("RGB")
    return g

def render_scene(name, fn, D):
    tmp = os.path.join(OUT, name + ".tmp.mp4"); final = os.path.join(OUT, name + ".mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                          "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    g = with_fades(fn, D)
    for i in range(int(D * FPS)):
        p.stdin.write(g(i / FPS).tobytes())
    p.stdin.close()
    if p.wait() == 0: os.replace(tmp, final)
    return final

if __name__ == "__main__":
    if sys.argv[1:] == ["stills"]:
        for name, fn, D in SCENES:
            for frac in (.55, .95):
                with_fades(fn, D)(D * frac).save(os.path.join(OUT, f"still_{name}_{int(frac*100)}.jpg"), quality=85)
    else:
        files = [render_scene(*s) for s in SCENES]
        lst = os.path.join(OUT, "list.txt")
        open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                        os.path.join(OUT, "gps_explainer_sample.mp4")], check=True)
        print("done")
