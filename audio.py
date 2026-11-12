"""Audio for Shorts: royalty-free procedural music, synthesized SFX, ducking and mixdown (48 kHz stereo).

Music: if assets/music/ contains .mp3/.wav/.ogg/.m4a tracks (e.g. from the YouTube Audio Library) one is
picked per Short; otherwise an original track is synthesized (so it is copyright-free by construction).
SFX: generated once into assets/sfx/*.wav; replace any of those files with your own to change the sound.
"""
import os, glob, subprocess, math
import numpy as np, soundfile as sf

SR = 48000
ROOT = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(ROOT, "assets", "music")
SFX_DIR = os.path.join(ROOT, "assets", "sfx")

def mtof(m): return 440.0 * 2 ** ((m - 69) / 12)
def _t(d): return np.arange(int(d * SR)) / SR

def _add(buf, start, sig, pan=0.0):
    i = int(start * SR)
    if i >= buf.shape[0] or i + len(sig) <= 0: return
    sig = sig[: buf.shape[0] - i]
    l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    buf[i:i + len(sig), 0] += sig * l * 1.414; buf[i:i + len(sig), 1] += sig * r * 1.414

def _lp(x, k):
    """Cheap low-pass: moving average of width k samples (cumsum)."""
    if k <= 1: return x
    c = np.cumsum(np.concatenate([[0.0], x])); y = (c[k:] - c[:-k]) / k
    return np.concatenate([y, np.full(k - 1, y[-1] if len(y) else 0.0)])

# ------------------------------------------------------------------ music
PROGS = [
    [(0, 3, 7), (8, 12, 15), (3, 7, 10), (10, 14, 17)],   # i VI III VII
    [(0, 3, 7), (5, 8, 12), (8, 12, 15), (7, 11, 14)],    # i iv VI V
    [(0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12)],    # I V vi IV
    [(0, 3, 7), (10, 14, 17), (8, 12, 15), (7, 10, 14)],  # i VII VI v
]

def synth_music(dur, seed=0):
    rng = np.random.default_rng(seed)
    bpm = int(rng.choice([112, 116, 120, 124, 128])); beat = 60 / bpm; bar = 4 * beat
    root = 45 + int(rng.integers(0, 8)); prog = PROGS[int(rng.integers(0, len(PROGS)))]
    arp_pat = [[0, 1, 2, 1], [0, 2, 1, 2], [0, 1, 2, 3], [2, 1, 0, 1]][int(rng.integers(0, 4))]
    N = int((dur + 2) * SR); buf = np.zeros((N, 2), np.float32)
    nb = int(math.ceil(dur / bar)) + 1
    for b in range(nb):
        t0 = b * bar; ch = prog[b % 4]
        # pad: soft additive saw, detuned L/R
        tt = _t(bar + .3); env = np.minimum(1, tt / .25) * np.exp(-tt * .25) * np.minimum(1, (bar + .3 - tt) / .3)
        for n in ch:
            f = mtof(root + 12 + n)
            for side, det in ((-0.6, .997), (0.6, 1.003)):
                s = sum(np.sin(2 * np.pi * f * det * k * tt) / k for k in range(1, 7))
                _add(buf, t0, (.018 * env * s).astype(np.float32), side)
        for q in range(4):
            tq = t0 + q * beat
            # kick
            tk = _t(.35); fk = 45 + 90 * np.exp(-tk * 30)
            _add(buf, tq, (.55 * np.sin(2 * np.pi * np.cumsum(fk) / SR) * np.exp(-tk * 9)).astype(np.float32))
            # snare / clap on 2 & 4
            if q in (1, 3):
                ts = _t(.22); nz = rng.standard_normal(len(ts))
                s = .16 * np.diff(nz, prepend=0) * np.exp(-ts * 22) + .12 * np.sin(2 * np.pi * 190 * ts) * np.exp(-ts * 30)
                _add(buf, tq, s.astype(np.float32), .05)
            # hats on off-beats
            for e in (0.5, 0.75) if q % 2 else (0.5,):
                th = _t(.05); hz = np.diff(rng.standard_normal(len(th)), prepend=0)
                _add(buf, tq + e * beat, (.05 * hz * np.exp(-th * 90)).astype(np.float32), .3)
            # bass eighths with sidechain-ish envelope
            for e in (0, .5):
                tb = _t(beat * .48); f = mtof(root - 12 + ch[0])
                s = np.tanh(1.8 * np.sin(2 * np.pi * f * tb)) * np.minimum(1, tb / .03) * np.exp(-tb * 5)
                _add(buf, tq + e * beat, (.16 * s).astype(np.float32))
            # pluck arp 16ths
            for e in range(4):
                n = ch[arp_pat[(q * 4 + e) % 4] % 3] + (12 if arp_pat[(q * 4 + e) % 4] == 3 else 0)
                ta = _t(.2); f = mtof(root + 24 + n)
                s = (2 / np.pi) * np.arcsin(np.sin(2 * np.pi * f * ta)) * np.exp(-ta * 18)
                _add(buf, tq + e * beat / 4, (.045 * s).astype(np.float32), -.45 if e % 2 else .45)
    buf = buf[: int(dur * SR)]
    return buf / (np.abs(buf).max() + 1e-6) * .9

def load_music(dur, seed=0):
    tracks = sorted(sum((glob.glob(os.path.join(MUSIC_DIR, e)) for e in ("*.mp3", "*.wav", "*.ogg", "*.m4a")), []))
    if not tracks: return synth_music(dur, seed), "synth"
    path = tracks[seed % len(tracks)]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    m = np.frombuffer(raw, np.float32).reshape(-1, 2)
    reps = int(math.ceil(dur * SR / len(m)))
    m = np.tile(m, (reps, 1))[: int(dur * SR)]
    return m / (np.abs(m).max() + 1e-6) * .9, os.path.basename(path)

# ------------------------------------------------------------------ sfx
def _sfx(name):
    rng = np.random.default_rng(7)
    if name == "whoosh":
        t = _t(.45); n = rng.standard_normal(len(t)); env = np.sin(np.pi * np.clip(t / .45, 0, 1)) ** 2
        lo, hi = _lp(n, 40), _lp(n, 6); k = np.sin(np.pi * t / .45)
        s = (lo * (1 - k) + hi * k) * env * 1.4
        return np.stack([s * (1 - t / .45 * .6), s * (.4 + t / .45 * .6)], 1)
    if name == "pop":
        t = _t(.12); f = 900 * np.exp(-t * 18) + 280
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 32)
    elif name == "click":
        t = _t(.05); s = (np.sin(2 * np.pi * 2400 * t) * .6 + rng.standard_normal(len(t)) * .4) * np.exp(-t * 120)
    elif name == "ding":
        t = _t(.7); s = (np.sin(2 * np.pi * 1318.5 * t) + .5 * np.sin(2 * np.pi * 1975.5 * t)) * np.exp(-t * 6) * .6
    elif name == "impact":
        t = _t(.8); f = 40 + 120 * np.exp(-t * 14)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5) + _lp(rng.standard_normal(len(t)), 8) * np.exp(-t * 25) * 1.5
    elif name in ("riser", "riser_short"):
        d = 1.4 if name == "riser" else .7; t = _t(d); x = t / d
        n = rng.standard_normal(len(t)); f = 220 + 1100 * x ** 2
        s = (_lp(n, 3) * .5 + .35 * np.sin(2 * np.pi * np.cumsum(f) / SR)) * x ** 2.2
    else:
        raise KeyError(name)
    return np.stack([s, s], 1)

SFX_GAIN = {"whoosh": .32, "pop": .42, "click": .30, "ding": .30, "impact": .55, "riser": .28, "riser_short": .2}

def sfx(name):
    os.makedirs(SFX_DIR, exist_ok=True)
    p = os.path.join(SFX_DIR, name + ".wav")
    if not os.path.exists(p):
        s = _sfx(name).astype(np.float32); s /= np.abs(s).max() + 1e-6; sf.write(p, s * .9, SR)
    a, sr = sf.read(p, dtype="float32", always_2d=True)
    if sr != SR:
        idx = np.arange(int(len(a) * SR / sr)) * sr / SR
        a = np.stack([np.interp(idx, np.arange(len(a)), a[:, c]) for c in range(a.shape[1])], 1)
    if a.shape[1] == 1: a = np.repeat(a, 2, 1)
    return a

# ------------------------------------------------------------------ mix
def resample(x, sr_in):
    """Resample mono float array to SR via ffmpeg (good quality)."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(sr_in), "-ac", "1", "-i", "-",
                        "-f", "f32le", "-ar", str(SR), "-ac", "1", "-"], input=x.astype(np.float32).tobytes(),
                       capture_output=True, check=True).stdout
    return np.frombuffer(p, np.float32).copy()

def mix(voice, dur, events, seed=0, music_gain=.17, duck_gain=.055):
    """voice: mono float @SR placed already; events: [(t, name)]. Returns stereo float32 (N, 2)."""
    N = int(round(dur * SR))
    v = np.zeros(N, np.float32); v[: min(N, len(voice))] = voice[:N]
    music, src = load_music(dur, seed)
    # ducking envelope from the voice
    e = _lp(np.abs(v).astype(np.float64), int(.03 * SR))
    e = _lp(np.clip(e / .04, 0, 1), int(.25 * SR))
    g = music_gain - (music_gain - duck_gain) * np.clip(e * 1.3, 0, 1)
    out = music[:N] * g[:, None] + v[:, None] * .92
    fx = np.zeros((N, 2), np.float32)
    for t, name in events:
        s = sfx(name) * SFX_GAIN.get(name, .3); i = int(t * SR)
        if name.startswith("riser"): i -= len(s)      # risers END on the event
        a, b = max(0, i), min(N, i + len(s))
        if b > a: fx[a:b] += s[a - i:b - i]
    out = out + fx
    return np.clip(out, -1, 1).astype(np.float32), src
