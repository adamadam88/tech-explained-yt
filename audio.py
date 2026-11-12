"""Audio for Tech, Explained: original generated music (no copyright), synthesized SFX,
voice ducking and the final mix. If assets/music/ contains .mp3/.wav tracks (e.g. from
the YouTube Audio Library), one of them is used instead of the generated score."""
import glob, math, os, subprocess
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt, resample_poly

SR = 48000


def resample(x, sr_in, sr_out):
    if sr_in == sr_out: return x.astype(np.float32)
    g = math.gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)

def lp(x, f, order=2): return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)
def hp(x, f, order=2): return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)
def bp(x, lo, hi, order=2): return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)
def db(v): return 10 ** (v / 20)
def midi(n): return 440.0 * 2 ** ((n - 69) / 12)


# ------------------------------------------------------------------ music
def generated_music(dur, seed=1):
    """Calm, driving electronic bed: pads + bass + pluck arpeggio + soft drums, in sections."""
    rng = np.random.default_rng(seed)
    progs = [[57, 53, 48, 55], [50, 53, 48, 55], [57, 52, 53, 55], [45, 53, 48, 52]]  # roots (A minor family)
    prog = progs[seed % len(progs)]
    bpm = [92, 96, 100][seed % 3]; beat = 60 / bpm; bar = 4 * beat
    n = int(dur * SR) + SR; out = np.zeros(n, np.float32)
    t_bar = np.arange(int(bar * SR)) / SR
    minor = {57: [0, 3, 7], 50: [0, 3, 7], 45: [0, 3, 7], 52: [0, 3, 7]}
    pad = np.zeros(n, np.float32); bass = np.zeros(n, np.float32); arp = np.zeros(n, np.float32); drums = np.zeros(n, np.float32)
    nb = int(dur / bar) + 2
    pl = int(0.35 * SR); tt = np.arange(pl) / SR
    kick_len = int(0.32 * SR); tk = np.arange(kick_len) / SR
    kick = np.sin(2 * np.pi * (45 * tk + (110 / 9) * (1 - np.exp(-9 * tk)))) * np.exp(-tk * 9)
    hat = hp(rng.normal(0, 1, int(0.05 * SR)), 7000) * np.exp(-np.arange(int(0.05 * SR)) / SR * 70)
    for b in range(nb):
        root = prog[b % 4]; ivs = minor.get(root, [0, 4, 7]); s0 = int(b * bar * SR)
        if s0 >= n: break
        L = min(len(t_bar), n - s0); tb = t_bar[:L]
        env = np.minimum(1, tb / 0.6) * np.minimum(1, (bar - tb) / 0.25 + 0.4)
        chord = np.zeros(L)
        for iv in ivs + [12]:
            f = midi(root + iv - 12)
            for det in (-0.12, 0.12):
                for h in range(1, 6):
                    chord += np.sin(2 * np.pi * f * (1 + det / 100) * h * tb + h) / (h * 1.6)
        pad[s0:s0 + L] += (chord * env * 0.05).astype(np.float32)
        section = (b // 8) % 4
        fb = midi(root - 24)
        for k in range(8):  # eighth-note bass
            st = s0 + int(k * beat / 2 * SR); ln = int(beat / 2 * SR * 0.9)
            if st + ln > n: break
            tl = np.arange(ln) / SR
            bass[st:st + ln] += (np.sin(2 * np.pi * fb * tl) + 0.3 * np.sin(4 * np.pi * fb * tl)) * np.exp(-tl * 5) * (0.22 if section else 0.12)
        if section in (1, 2, 3):
            notes = [root + i for i in ivs] + [root + 12, root + ivs[1] + 12]
            for k in range(16):
                st = s0 + int(k * beat / 4 * SR)
                if st + pl > n: break
                f = midi(notes[(k * 3 + b) % len(notes)] + 12)
                tone = (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 14)
                arp[st:st + pl] += tone * (0.05 if k % 4 == 0 else 0.032)
        if b >= 4 and section != 0:
            for k in range(4):
                st = s0 + int(k * beat * SR)
                if k % 2 == 0 and st + kick_len <= n: drums[st:st + kick_len] += kick * 0.38
                hs = st + int(beat / 2 * SR)
                if hs + len(hat) <= n: drums[hs:hs + len(hat)] += hat * 0.05
    pad = lp(pad, 1400); arp = lp(arp, 4200)
    mus = pad + bass + arp + drums
    mus = lp(mus, 9000)
    st = np.stack([mus, mus], 1)
    d = int(0.011 * SR); st[d:, 1] = 0.8 * st[d:, 1] + 0.2 * np.concatenate([np.zeros(d), arp])[:n - d] + 0.0  # width
    st = st[:int(dur * SR)]
    fi, fo = int(1.5 * SR), int(3 * SR)
    st[:fi] *= np.linspace(0, 1, fi)[:, None]; st[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return st / (np.abs(st).max() + 1e-9) * 0.8

def load_music(music_dir, dur, seed):
    files = sorted(glob.glob(os.path.join(music_dir, "*.mp3")) + glob.glob(os.path.join(music_dir, "*.wav")))
    if not files: return generated_music(dur, seed)
    f = files[seed % len(files)]
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", f, "-t", str(dur), "-f", "f32le",
                                   "-ac", "2", "-ar", str(SR), "-"])
    st = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    fo = int(3 * SR); st[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return st / (np.abs(st).max() + 1e-9) * 0.8


# ------------------------------------------------------------------ sfx
def sfx(kind, rng):
    if kind == "whoosh":
        L = int(0.55 * SR); t = np.arange(L) / SR; x = rng.normal(0, 1, L)
        out = np.zeros(L); seg = L // 12
        for k in range(12):
            fc = 300 + 2600 * math.sin(math.pi * (k + 0.5) / 12) ** 2
            y = bp(x, fc * 0.6, min(fc * 1.6, 20000))
            w = np.zeros(L); a, b = max(0, k * seg - seg // 2), min(L, (k + 1) * seg + seg // 2)
            w[a:b] = np.hanning(b - a); out += y * w
        env = np.sin(np.pi * np.clip(t / 0.55, 0, 1)) ** 2
        return (out * env / (np.abs(out).max() + 1e-9) * 0.9).astype(np.float32)
    if kind == "pop":
        L = int(0.12 * SR); t = np.arange(L) / SR
        f = 900 * np.exp(-t * 18) + 380
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 32) * 0.8).astype(np.float32)
    if kind == "click":
        L = int(0.04 * SR); t = np.arange(L) / SR
        return ((np.sin(2 * np.pi * 2600 * t) * 0.6 + rng.normal(0, 0.3, L)) * np.exp(-t * 140)).astype(np.float32)
    if kind == "impact":
        L = int(0.9 * SR); t = np.arange(L) / SR
        boom = np.sin(2 * np.pi * (40 * t + 40 / 6 * (1 - np.exp(-6 * t)))) * np.exp(-t * 4.5)
        noise = lp(rng.normal(0, 1, L), 1800) * np.exp(-t * 10) * 0.5
        return ((boom + noise) * 0.9).astype(np.float32)
    raise ValueError(kind)

def place(track, x, at, gain):
    s = int(at * SR)
    if s >= len(track): return
    e = min(len(track), s + len(x)); track[s:e] += x[:e - s] * gain


# ------------------------------------------------------------------ mix
def build_mix(jobs, total, out_path, seed=1, music_dir=None):
    import render as R
    n = int(total * SR) + SR // 10
    voice = np.zeros(n, np.float32)
    for j in jobs:
        x, sr = sf.read(j["wav"], dtype="float32")
        if x.ndim > 1: x = x.mean(1)
        x = resample(x, sr, SR); x = x / (np.abs(x).max() + 1e-9) * db(-3)
        place(voice, x, j["t0"] + j["lead"], 1.0)
    voice = hp(voice, 70).astype(np.float32)
    rng = np.random.default_rng(seed); fx = np.zeros(n, np.float32)
    last = -9
    for j in jobs:
        tr = j["spec"].get("transition", "zoom")
        if tr == "flash": place(fx, sfx("impact", rng), j["t0"], db(-11))
        if tr != "cut": place(fx, sfx("whoosh", rng), max(0, j["t0"] - 0.22), db(-15))
        S = R.Scene(j); kind = "click" if j["spec"]["visual_type"] in ("top_list", "timeline", "broadcast", "tiles") else "pop"
        for c in S.all_cues():
            at = j["t0"] + c
            if c <= 0.05 or at - last < 0.7: continue
            place(fx, sfx(kind, rng), at, db(-21 if kind == "pop" else -17)); last = at
    music = load_music(music_dir or "", total + 0.1, seed)
    music = np.pad(music, ((0, max(0, n - len(music))), (0, 0)))[:n]
    # ducking: music sits ~18 dB under the voice while it speaks, comes up in the gaps
    env = np.abs(voice); win = int(0.05 * SR)
    env = np.convolve(env, np.ones(win) / win, "same")
    active = (env > db(-40)).astype(np.float32)
    k = int(0.25 * SR); sm = np.convolve(active, np.ones(k) / k, "same")
    vr = np.sqrt(np.mean(voice[voice != 0] ** 2)) if np.any(voice) else 0.1
    mr = np.sqrt(np.mean(music ** 2)) + 1e-9
    g_duck = vr * db(-18) / mr; g_open = vr * db(-10) / mr
    gain = g_open + (g_duck - g_open) * np.clip(sm * 1.5, 0, 1)
    mix = music * gain[:, None] + (voice + fx)[:, None]
    peak = np.abs(mix).max()
    if peak > db(-1): mix *= db(-1) / peak
    tmp = out_path + ".raw.wav"; sf.write(tmp, mix.astype(np.float32), SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), out_path], check=True)
    os.remove(tmp)
    return out_path
