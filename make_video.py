#!/usr/bin/env python3
"""Tech, Explained — one command, one finished video.

    python make_video.py "How does GPS know where you are?"
    python make_video.py                # next 'todo' topic in topics.csv
    python make_video.py --stills       # only render QA keyframes (fast check)

Needs scripts/<slug>.json (written & fact-checked by Claude Code). Produces
output/<date>_<slug>/{video.mp4, short.mp4, thumbnail.jpg, title.txt,
description.txt, tags.txt, script.md}.
"""
import argparse, csv, datetime, difflib, glob, hashlib, json, math, os, re, subprocess, sys, time
from multiprocessing import Pool
import numpy as np, soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import render as R
import audio as A

MODELS = os.path.join(ROOT, "models")
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FPS = R.FPS
MAX_MB = 95


def slugify(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]
def sh(cmd): subprocess.run(cmd, check=True)
def log(*a): print(time.strftime("[%H:%M:%S]"), *a, flush=True)
def ffdur(p): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).decode().strip())


# ------------------------------------------------------------------ topic / script
def pick_topic(arg):
    if arg: return arg
    with open(os.path.join(ROOT, "topics.csv")) as f:
        for row in csv.DictReader(f):
            if row["status"].strip() == "todo": return row["topic"]
    sys.exit("No 'todo' topics left in topics.csv")

def mark_done(topic):
    p = os.path.join(ROOT, "topics.csv")
    rows = list(csv.DictReader(open(p)))
    for r in rows:
        if r["topic"] == topic: r["status"] = "done"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, ["topic", "status"]); w.writeheader(); w.writerows(rows)


# ------------------------------------------------------------------ voice
def ensure_models():
    os.makedirs(MODELS, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(MODELS, f)
        if not os.path.exists(p):
            log("downloading", f); sh(["curl", "-sSL", "--fail", "-o", p, KOKORO_URL + f])

def trim_silence(x, sr, thr_db=-42, keep=0.04):
    env = np.abs(x); thr = 10 ** (thr_db / 20) * max(1e-6, env.max())
    idx = np.where(env > thr)[0]
    if len(idx) == 0: return x
    a = max(0, idx[0] - int(keep * sr)); b = min(len(x), idx[-1] + int(keep * sr * 3))
    return x[a:b]

def tts(scenes, voice, speed, work):
    from kokoro_onnx import Kokoro
    k = None; out = []
    for i, sc in enumerate(scenes):
        h = hashlib.md5(f"{voice}|{speed}|{sc['narration']}".encode()).hexdigest()[:10]
        p = os.path.join(work, "tts", f"{i:02d}_{h}.wav")
        if not os.path.exists(p):
            if k is None: k = Kokoro(os.path.join(MODELS, "kokoro-v1.0.onnx"), os.path.join(MODELS, "voices-v1.0.bin"))
            s, sr = k.create(sc["narration"], voice=sc.get("voice", voice), speed=speed, lang="en-us")
            s = trim_silence(np.asarray(s, np.float32), sr)
            os.makedirs(os.path.dirname(p), exist_ok=True); sf.write(p, s, sr)
        out.append(p)
    return out


# ------------------------------------------------------------------ word timings
def norm(w): return re.sub(r"[^a-z0-9]", "", w.lower())

def align(narr_tokens, wh):
    """Map every narration token to a (start, end) using whisper words; interpolate gaps."""
    a = [norm(t) for t in narr_tokens]; b = [norm(w[0]) for w in wh]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    times = [None] * len(a)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size): times[blk.a + k] = (wh[blk.b + k][1], wh[blk.b + k][2])
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and j2 > j1:   # e.g. "kilometers" vs "km": spread the whisper span
            s, e = wh[j1][1], wh[j2 - 1][2]; L = sum(len(x) + 1 for x in a[i1:i2]); acc = 0
            for i in range(i1, i2):
                l = len(a[i]) + 1; times[i] = (s + (e - s) * acc / L, s + (e - s) * (acc + l) / L); acc += l
    # remaining holes: interpolate between neighbours
    n = len(times); i = 0
    while i < n:
        if times[i] is None:
            j = i
            while j < n and times[j] is None: j += 1
            s = times[i - 1][1] if i > 0 else (wh[0][1] if wh else 0)
            e = times[j][0] if j < n else (wh[-1][2] if wh else s + 0.3 * (j - i))
            if e <= s: e = s + 0.25 * (j - i)
            for k in range(i, j):
                times[k] = (s + (e - s) * (k - i) / (j - i), s + (e - s) * (k - i + 1) / (j - i))
            i = j
        else: i += 1
    # monotonic
    for i in range(1, n):
        if times[i][0] < times[i - 1][0]: times[i] = (times[i - 1][0] + 0.05, max(times[i][1], times[i - 1][0] + 0.1))
    return times

def word_timings(scenes, wavs, work):
    from faster_whisper import WhisperModel
    m = None; res = []
    for sc, p in zip(scenes, wavs):
        j = p.replace(".wav", ".words.json")
        if not os.path.exists(j):
            if m is None: m = WhisperModel("base.en", device="cpu", compute_type="int8")
            x, sr = sf.read(p, dtype="float32")
            x16 = A.resample(x, sr, 16000)
            segs, _ = m.transcribe(x16, word_timestamps=True, language="en", beam_size=5)
            wh = [(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in s.words]
            toks = sc["narration"].split()
            tt = align(toks, wh)
            json.dump({"whisper": wh, "words": [{"w": t, "s": a, "e": b} for t, (a, b) in zip(toks, tt)]}, open(j, "w"), indent=0)
        res.append(json.load(open(j))["words"])
    return res


# ------------------------------------------------------------------ planning
def plan(script, wavs, words):
    scenes = script["scenes"]; jobs = []; t0 = 0.0; chapters = []; label = None; chap_n = 0
    for i, (sc, wv, ws) in enumerate(zip(scenes, wavs, words)):
        speech = sf.info(wv).duration
        lead = 0.12 if i == 0 else 0.32; tail = 0.55
        frames = int(round((lead + speech + tail) * FPS)); dur = frames / FPS
        if sc.get("chapter"):
            chap_n += 1; label = f"{chap_n:02d} · {sc['chapter'].upper()}"; chapters.append((t0, sc["chapter"]))
        jobs.append(dict(spec=sc, idx=i, t0=t0, dur=dur, frames=frames, lead=lead, wav=wv, chapter_label=label,
                         words=[{"w": w["w"], "s": w["s"] + lead, "e": w["e"] + lead} for w in ws]))
        t0 += dur
    for j in jobs:
        j["total"] = t0; j["chapter_starts"] = [c[0] for c in chapters[1:]]
    return jobs, chapters, t0

def pacing_report(jobs):
    """Rule check: something new on screen at least every ~4 s (cues + transitions)."""
    worst = []
    for j in jobs:
        S = R.Scene(j); ev = sorted(set([0.0] + [c for c in S.all_cues() if 0 <= c <= j["dur"]] + [j["dur"]]))
        gaps = [(b - a, a) for a, b in zip(ev, ev[1:])]
        g, at = max(gaps)
        if g > 4.5: worst.append(f"scene {j['idx']:02d} ({j['spec']['visual_type']}): {g:.1f}s without a new element at {at:.1f}s")
    return worst


# ------------------------------------------------------------------ metadata
def ts(s): s = int(s); return f"{s // 60}:{s % 60:02d}"

def write_meta(script, chapters, jobs, total, out):
    open(os.path.join(out, "title.txt"), "w").write(script["title"].strip() + "\n")
    lines = [script["description_intro"].strip(), "", "CHAPTERS"]
    lines += [f"{ts(t)} {name}" for t, name in chapters]
    lines += ["", "SOURCES"] + [f"• {s['label']}: {s['url']}" for s in script["sources"]]
    if script.get("next_video"): lines += ["", f"Watch next: {script['next_video']}"]
    lines += ["", "Music and sound effects: original, generated for this channel (no copyright).",
              "Narration: synthetic voice (Kokoro TTS). Graphics are illustrative animations, not real footage.", "",
              "#" + " #".join(re.sub(r'[^A-Za-z0-9]', '', t.title()) for t in script["tags"][:3])]
    open(os.path.join(out, "description.txt"), "w").write("\n".join(lines) + "\n")
    tags, n = [], 0
    for t in script["tags"]:
        if n + len(t) + 1 > 480: break
        tags.append(t); n += len(t) + 1
    open(os.path.join(out, "tags.txt"), "w").write(", ".join(tags) + "\n")
    md = [f"# {script['title']}", "", f"Topic: {script['topic']} · Voice: {script.get('voice')} · Length: {ts(total)}", ""]
    for j in jobs:
        sc = j["spec"]
        if sc.get("chapter"): md += [f"## {sc['chapter']}", ""]
        md += [f"**[{ts(j['t0'])}] {sc['visual_type']}** — {sc['narration']}", ""]
    md += ["## Sources", ""] + [f"- [{s['label']}]({s['url']})" for s in script["sources"]]
    open(os.path.join(out, "script.md"), "w").write("\n".join(md) + "\n")


# ------------------------------------------------------------------ thumbnail
def thumbnail(script, path):
    import cv2
    from PIL import Image
    tb = script["thumbnail"]; theme = tb.get("theme", "navy"); th = R.THEMES[theme]
    img = R.bg_base(theme).copy()
    R.blit(img, R.glow_sprite(700, th["acc"]), 1500 - 700, 540 - 700, 0.35)
    R.globe_frame(img, 1460, 560, 380, -10, 18, theme, 2.0, True, 6, (40.4, -3.7), 1.0, 1.0)
    words = tb["words"]; y = 200 if len(words) < 3 else 140
    if tb.get("kicker"):
        R.pill(img, tb["kicker"], 110, y + 10, 52, th["acc2"], anchor="l", fill=(10, 14, 26, 240)); y += 110
    for i, w in enumerate(words):
        size = R.fit(w, 400 if i == 0 else 230, 860, "Black")
        col = R.WHITE if i == 0 else th["acc"]
        R.txt(img, w, 100, y + size * 0.55, size, "Black", col, 1, "lm", glow=(0, 0, 0))
        R.txt(img, w, 100, y + size * 0.55, size, "Black", col, 1, "lm", glow=th["acc"] if i else None)
        y += size * 1.05
    cv2.rectangle(img, (0, 0), (R.W - 1, R.H - 1), th["acc"], 14)
    Image.fromarray(img).resize((1280, 720), Image.LANCZOS).save(path, quality=92)


# ------------------------------------------------------------------ short
def make_short(script, jobs, scene_files, mix_wav, out_dir, work):
    sel = script.get("short") or []
    if not sel: return None
    sel = [i for i in sel if i < len(jobs)]
    if sum(jobs[i]["dur"] for i in sel) > 58: return None
    lst = os.path.join(work, "short_list.txt")
    open(lst, "w").write("".join(f"file '{scene_files[i]}'\n" for i in sel))
    sv = os.path.join(work, "short_silent.mp4")
    sh(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", sv])
    x, sr = sf.read(mix_wav, dtype="float32")
    parts = [x[int(jobs[i]["t0"] * sr):int((jobs[i]["t0"] + jobs[i]["dur"]) * sr)] for i in sel]
    sa = np.concatenate(parts); fl = int(0.4 * sr); sa[-fl:] *= np.linspace(1, 0, fl)[:, None] if sa.ndim > 1 else np.linspace(1, 0, fl)
    swav = os.path.join(work, "short_audio.wav"); sf.write(swav, sa, sr)
    # header image
    from PIL import Image
    th = R.THEMES[jobs[sel[0]]["spec"].get("theme", "navy")]
    hdr = np.zeros((560, 1080, 3), np.uint8)
    size, lines = R.fit_wrap(script.get("short_title", script["topic"]), 92, 980, 3, "Black")
    y = 300 - len(lines) * size * 0.58
    for l in lines: R.txt(hdr, l, 540, y + size * 0.55, size, "Black", R.WHITE, 1, "mm"); y += size * 1.15
    R.txt(hdr, "TECH, EXPLAINED", 540, 90, 40, "Bold", th["acc"], 1)
    hp = os.path.join(work, "short_header.png"); Image.fromarray(hdr).save(hp)
    out = os.path.join(out_dir, "short.mp4")
    fc = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:3,eq=brightness=-0.25[bg];"
          "[0:v]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2+120[v1];[v1][2:v]overlay=0:120[v]")
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", sv, "-i", swav, "-loop", "1", "-i", hp, "-filter_complex", fc,
        "-map", "[v]", "-map", "1:a", "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-maxrate", "6M",
        "-bufsize", "12M", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out])
    return out


# ------------------------------------------------------------------ stills / QA
def stills(jobs, work, only=None):
    d = os.path.join(work, "stills"); os.makedirs(d, exist_ok=True)
    for f in glob.glob(os.path.join(d, "*.jpg")): os.remove(f)
    tasks = []
    for j in jobs:
        if only is not None and j["idx"] not in only: continue
        S = R.Scene(j); cues = [c for c in S.all_cues() if 0 < c < j["dur"]]
        times = sorted(set([round(min(j["dur"] - 0.05, c + 0.6), 2) for c in cues[-2:]] + [round(j["dur"] * 0.5, 2), 0.2]))
        for t in times: tasks.append((j, t, os.path.join(d, f"s{j['idx']:02d}_{t:05.2f}.jpg")))
    with Pool(4) as p: p.starmap(R.still, tasks)
    contact_sheets(d)
    return d

def contact_sheets(d):
    """3x3 grids of the QA stills (work/<slug>/stills/sheet_XX.jpg) for quick visual review."""
    from PIL import Image, ImageDraw
    fs = sorted(f for f in glob.glob(os.path.join(d, "s*.jpg")))
    for k in range(0, len(fs), 9):
        sheet = Image.new("RGB", (1920, 1080), "black")
        for i, f in enumerate(fs[k:k + 9]):
            im = Image.open(f).resize((640, 360))
            ImageDraw.Draw(im).text((8, 340), os.path.basename(f), fill=(255, 255, 0))
            sheet.paste(im, ((i % 3) * 640, (i // 3) * 360))
        sheet.save(os.path.join(d, f"sheet_{k // 9:02d}.jpg"), quality=85)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", nargs="?")
    ap.add_argument("--stills", action="store_true", help="only render QA keyframes")
    ap.add_argument("--scenes", help="comma list of scene indices for --stills")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    topic = pick_topic(a.topic); slug = slugify(topic)
    sp = os.path.join(ROOT, "scripts", slug + ".json")
    if not os.path.exists(sp):
        sys.exit(f"Missing {sp}\nAsk Claude Code: 'escribe el guion de \"{topic}\"' (it researches, fact-checks and writes it).")
    script = json.load(open(sp)); log("topic:", topic)
    work = os.path.join(ROOT, "work", slug); os.makedirs(work, exist_ok=True)

    ensure_models()
    log("voice (Kokoro)…"); wavs = tts(script["scenes"], script.get("voice", "af_heart"), script.get("speed", 1.0), work)
    log("word timings (faster-whisper)…"); words = word_timings(script["scenes"], wavs, work)
    jobs, chapters, total = plan(script, wavs, words)
    log(f"{len(jobs)} scenes, {total / 60:.2f} min")
    for w in pacing_report(jobs): log("  pacing:", w)

    if a.stills:
        only = [int(x) for x in a.scenes.split(",")] if a.scenes else None
        log("stills →", stills(jobs, work, only)); return

    # bitrate budget so video.mp4 stays < MAX_MB
    vb = int(min(4.0e6, (MAX_MB * 0.88 * 8e6) / total - 192e3))
    sdir = os.path.join(work, "scenes"); os.makedirs(sdir, exist_ok=True)
    for f in glob.glob(os.path.join(sdir, "*.mp4")): os.remove(f)
    for j in jobs:
        j["out"] = os.path.join(sdir, f"s{j['idx']:02d}.mp4"); j["maxrate"] = str(vb); j["bufsize"] = str(vb * 2); j["crf"] = 20
    log(f"rendering scenes (maxrate {vb / 1e6:.2f} Mbps)…")
    t = time.time()
    with Pool(a.workers) as p:
        files = []
        for k, f in enumerate(p.imap(R.render_scene, sorted(jobs, key=lambda j: -j["frames"]))):
            files.append(f); log(f"  {k + 1}/{len(jobs)} {os.path.basename(f)}")
    files = [j["out"] for j in jobs]
    log(f"scenes done in {(time.time() - t) / 60:.1f} min")
    lst = os.path.join(work, "list.txt"); open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    silent = os.path.join(work, "video_silent.mp4")
    sh(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent])

    log("audio mix (voice + music + sfx)…")
    mix_wav = os.path.join(work, "mix.wav")
    A.build_mix(jobs, total, mix_wav, seed=int(hashlib.md5(slug.encode()).hexdigest()[:6], 16),
                music_dir=os.path.join(ROOT, "assets", "music"))

    out = os.path.join(ROOT, "output", f"{datetime.date.today().isoformat()}_{slug}"); os.makedirs(out, exist_ok=True)
    video = os.path.join(out, "video.mp4")
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", mix_wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", video])
    mb = os.path.getsize(video) / 1e6; log(f"video.mp4: {mb:.1f} MB, {ffdur(video) / 60:.2f} min")
    if mb >= MAX_MB: log("!! video over size limit — lower the bitrate budget and re-run")

    thumbnail(script, os.path.join(out, "thumbnail.jpg"))
    write_meta(script, chapters, jobs, total, out)
    s = make_short(script, jobs, files, mix_wav, out, work)
    if s: log(f"short.mp4: {os.path.getsize(s) / 1e6:.1f} MB, {ffdur(s):.1f} s")
    mark_done(topic)
    log("done →", out)


if __name__ == "__main__":
    main()
