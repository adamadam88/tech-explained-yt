"""Audio for Shorts: royalty-free procedural music, synthesized SFX, ducking and mixdown (48 kHz stereo).

Music: ambient / minimal electronic. If assets/music/ contains .mp3/.wav/.ogg/.m4a tracks (e.g. from the YouTube Audio Library) one is
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

# ------------------------------------------------------------------ music (ambient / minimal electronic)
PROGS = [
    [(0, 7, 10, 15), (8, 15, 19, 24), (3, 10, 14, 19), (10, 17, 22, 26)],   # i(add9)  VImaj7  IIImaj7  VII
    [(0, 7, 14, 15), (5, 12, 15, 20), (8, 15, 19, 22), (7, 14, 17, 22)],    # i9  iv  VI  v
    [(0, 7, 11, 16), (9, 16, 19, 24), (5, 12, 16, 21), (7, 14, 19, 23)],    # Imaj7  vi  IV  V
]

def reverb(x, secs=2.6, mix=.35, seed=1):
    """Stereo convolution reverb with a decaying-noise impulse (FFT)."""
    rng = np.random.default_rng(seed); n = int(secs * SR); tt = np.arange(n) / SR
    out = np.empty_like(x)
    for c in range(2):
        ir = rng.standard_normal(n) * np.exp(-tt * 3.2 / secs * 2.3); ir = _lp(ir, 3); ir /= np.sqrt((ir ** 2).sum())
        L = len(x) + n; N = 1 << (L - 1).bit_length()
        wet = np.fft.irfft(np.fft.rfft(x[:, c], N) * np.fft.rfft(ir, N), N)[:len(x)]
        out[:, c] = x[:, c] * (1 - mix) + wet * mix
    return out

def synth_music(dur, seed=0):
    rng = np.random.default_rng(seed)
    bpm = int(rng.choice([88, 92, 96, 100])); beat = 60 / bpm; bar = 4 * beat
    root = 45 + int(rng.integers(0, 7)); prog = PROGS[int(rng.integers(0, len(PROGS)))]
    N = int((dur + 3) * SR); dry = np.zeros((N, 2), np.float32); drums = np.zeros((N, 2), np.float32)
    nb = int(math.ceil(dur / bar)) + 1
    for b in range(nb):
        t0 = b * bar; ch = prog[(b // 2) % 4]                       # one chord every two bars
        if b % 2 == 0:                                              # soft pad, slow attack/release
            d = 2 * bar + 1.5; tt = _t(d)
            env = np.minimum(1, tt / 1.6) * np.minimum(1, (d - tt) / 1.5)
            for n in ch:
                f = mtof(root + 12 + n)
                for side, det in ((-.7, .9975), (.7, 1.0025)):
                    s = np.sin(2 * np.pi * f * det * tt) + .18 * np.sin(4 * np.pi * f * det * tt)
                    _add(dry, t0, (.03 * env * s).astype(np.float32), side)
            ts = _t(2 * bar); f = mtof(root - 12 + ch[0])           # warm sub
            _add(dry, t0, (.12 * np.sin(2 * np.pi * f * ts) * np.minimum(1, ts / .4) * np.minimum(1, (2 * bar - ts) / .4)).astype(np.float32))
        for e in range(8):                                          # sparse glassy plucks (8ths)
            if rng.random() < .45: continue
            n = ch[int(rng.integers(0, len(ch)))] + 24; ta = _t(.9); f = mtof(root + n)
            s = (np.sin(2 * np.pi * f * ta) + .3 * np.sin(2 * np.pi * 2 * f * ta)) * np.exp(-ta * 5.5)
            _add(dry, t0 + e * beat / 2, (.035 * s).astype(np.float32), float(rng.uniform(-.6, .6)))
        if b >= 1:                                                  # felt kick on 1 & 3, whisper hats
            for q in (0, 2):
                tk = _t(.3); fk = 42 + 50 * np.exp(-tk * 25)
                _add(drums, t0 + q * beat, (.22 * np.sin(2 * np.pi * np.cumsum(fk) / SR) * np.exp(-tk * 11)).astype(np.float32))
            for e in range(8):
                th = _t(.03); hz = np.diff(rng.standard_normal(len(th)), prepend=0)
                _add(drums, t0 + (e + .5) * beat / 2, (.012 * rng.uniform(.5, 1) * hz * np.exp(-th * 140)).astype(np.float32), .35)
    buf = reverb(dry, 3.0, .45) + reverb(drums, 1.0, .12, 2)
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

# ------------------------------------------------------------------ sfx (subtle)
def _sfx(name):
    rng = np.random.default_rng(7)
    if name == "swish":                       # soft air movement on cuts
        d = .32; t = _t(d); n = rng.standard_normal(len(t)); k = np.sin(np.pi * t / d) ** 3
        s = (_lp(n, 22) * (1 - k * .6) + _lp(n, 9) * k * .6) * k * 2.2
        return np.stack([s * (1 - .4 * t / d), s * (.6 + .4 * t / d)], 1)
    if name == "tick":                        # tiny, clean UI click
        t = _t(.035); s = (np.sin(2 * np.pi * 3200 * t) * .5 + np.sin(2 * np.pi * 1600 * t) * .5) * np.exp(-t * 170)
    elif name == "chime":                     # soft glass tone for the key moments
        t = _t(1.6); s = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * dcy) for f, a, dcy in ((1046.5, .6, 3.2), (1568, .3, 4.5), (2093, .12, 6)))
        s = s * np.minimum(1, t / .008)
    elif name == "rise":                      # gentle swell into the reveal
        d = 1.2; t = _t(d); x = t / d; n = rng.standard_normal(len(t))
        s = (_lp(n, 12) * .6 + .2 * np.sin(2 * np.pi * np.cumsum(300 + 500 * x ** 2) / SR)) * x ** 2.5 * (1 - smooth_end(x))
    else:
        raise KeyError(name)
    return np.stack([s, s], 1)

def smooth_end(x): return np.clip((x - .94) / .06, 0, 1)

SFX_GAIN = {"swish": .10, "tick": .10, "chime": .085, "rise": .12}

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

def mix(voice, dur, events, seed=0, music_gain=.20, duck_gain=.075):
    """voice: mono float @SR placed already; events: [(t, name)]. Returns stereo float32 (N, 2)."""
    N = int(round(dur * SR))
    v = np.zeros(N, np.float32); v[: min(N, len(voice))] = voice[:N]
    music, src = load_music(dur, seed)
    if len(music) < N: music = np.concatenate([music, np.zeros((N - len(music), 2), music.dtype)])
    # ducking envelope from the voice
    e = _lp(np.abs(v).astype(np.float64), int(.03 * SR))
    e = _lp(np.clip(e / .04, 0, 1), int(.25 * SR))
    g = music_gain - (music_gain - duck_gain) * np.clip(e * 1.3, 0, 1)
    out = music[:N] * g[:, None] + v[:, None] * .92
    fx = np.zeros((N, 2), np.float32)
    for t, name in events:
        s = sfx(name) * SFX_GAIN.get(name, .3); i = int(t * SR)
        if name == "rise": i -= len(s)               # the swell ENDS on the event
        a, b = max(0, i), min(N, i + len(s))
        if b > a: fx[a:b] += s[a - i:b - i]
    out = out + fx
    return np.clip(out, -1, 1).astype(np.float32), src
