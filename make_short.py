#!/usr/bin/env python3
"""Quiet Circuit (@quietcircuit) — one-command YouTube Shorts pipeline.

  python make_short.py "How does GPS know where you are?"   # that topic (needs scripts/<slug>.json)
  python make_short.py                                       # next `todo` topic in topics.csv
  python make_short.py --batch 5                             # next 5 todo topics
  python make_short.py "<topic>" --review                    # only voice + timings + keyframe sheets (fast)

Pipeline: script.json (written by Claude, facts verified) -> Kokoro TTS per beat -> faster-whisper word
timestamps -> 3D hero objects (studio3d.cjs, Three.js) -> one mp4 per beat (engine.py, 1080x1920@60) -> concat -c copy -> music+SFX+ducking mix ->
mux -c:v copy (AAC, loudnorm -14 LUFS). Design system: STYLE.md -> thumbnail/title/description/tags/script.md in output/<date>_<slug>/.
"""
import argparse, csv, datetime, difflib, hashlib, json, os, re, shutil, subprocess, sys
from multiprocessing import Pool
import numpy as np, soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS, OUTPUT, BUILD, MODELS = (os.path.join(ROOT, d) for d in ("scripts", "output", "build", "models"))
TOPICS = os.path.join(ROOT, "topics.csv")
FPS = 60
MAX_MB = 95

def log(*a): print("»", *a, flush=True)
def slugify(s): return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", "")).strip("-")[:60]

# ------------------------------------------------------------------ topics
def read_topics():
    with open(TOPICS, newline="", encoding="utf-8") as f: return list(csv.DictReader(f))

def write_topics(rows):
    with open(TOPICS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["topic", "status"]); w.writeheader(); w.writerows(rows)

def made_slugs():
    s = set()
    if os.path.isdir(OUTPUT):
        for d in os.listdir(OUTPUT):
            m = re.match(r"\d{4}-\d{2}-\d{2}_(.+)", d)
            if m and os.path.exists(os.path.join(OUTPUT, d, "short.mp4")): s.add(m.group(1))
    return s

def next_todos(n):
    done = made_slugs()
    return [r["topic"] for r in read_topics() if r["status"].strip() == "todo" and slugify(r["topic"]) not in done][:n]

def mark_done(topic):
    rows = read_topics(); hit = False
    for r in rows:
        if r["topic"].strip().lower() == topic.strip().lower(): r["status"] = "done"; hit = True
    if not hit: rows.append({"topic": topic, "status": "done"})
    write_topics(rows)
    left = sum(r["status"].strip() == "todo" for r in rows)
    if left < 5: log(f"AVISO: quedan {left} temas 'todo' -> Claude debe investigar y añadir 20 nuevos a topics.csv")

# ------------------------------------------------------------------ voice
_kokoro = None
def kokoro():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(os.path.join(MODELS, "kokoro-v1.0.onnx"), os.path.join(MODELS, "voices-v1.0.bin"))
    return _kokoro

def trim(a, sr, thr=.012, pad=.025):
    idx = np.where(np.abs(a) > thr)[0]
    if not len(idx): return a
    return a[max(0, idx[0] - int(pad * sr)): idx[-1] + int(pad * 1.6 * sr)]

def tts_beats(beats, voice, speed, work):
    out = []
    os.makedirs(os.path.join(work, "voice"), exist_ok=True)
    for i, b in enumerate(beats):
        say = b.get("say") or b["narration"].replace("*", "")
        key = hashlib.md5(f"{say}|{voice}|{speed}".encode()).hexdigest()[:10]
        p = os.path.join(work, "voice", f"{i:02d}_{key}.wav")
        if not os.path.exists(p):
            a, sr = kokoro().create(say, voice=voice, speed=speed, lang="en-us")
            sf.write(p, trim(a, sr), sr)
        a, sr = sf.read(p, dtype="float32"); out.append((a, sr, p))
    return out

# ------------------------------------------------------------------ word timings
_whisper = None
def whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _whisper

def norm(s): return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("-", " "))

def display_words(narr):
    import engine
    return [{"text": w, "key": k} for w, k in engine.tokens(narr)]

def _key(w): return re.sub(r"[^a-z0-9]", "", w.lower())

def align(disp, ww, dur):
    """Give each displayed word a start/end from whisper's word times.
    Words that match (difflib anchors) take whisper's times exactly; the rest (e.g. '0.07' heard as '0' '.07',
    or whisper hallucinations like a trailing 'Thank you') are interpolated by character length between anchors."""
    n = len(disp)
    ww = [x for x in ww if x[1] < dur - .02]
    if ww:
        sm = difflib.SequenceMatcher(None, [_key(w["text"]) for w in disp], [_key(x[0]) for x in ww], autojunk=False)
        anchors = {}
        for blk in sm.get_matching_blocks():
            for k in range(blk.size): anchors[blk.a + k] = ww[blk.b + k]
    else:
        anchors = {}
    # anchor points in "character space" -> time
    L = np.cumsum([0] + [len(w["text"]) + 1 for w in disp]).astype(float)
    P, T = [0.0], [ww[0][1] if ww and 0 not in anchors else (anchors[0][1] if 0 in anchors else 0.0)]
    for i in sorted(anchors):
        P += [L[i], L[i + 1] - 1]; T += [anchors[i][1], anchors[i][2]]
    end = max([x[2] for x in ww] + [T[-1]]) if ww else dur * .95
    P.append(L[-1]); T.append(max(T[-1], min(end, dur)))
    P, T = np.array(P), np.maximum.accumulate(np.array(T))
    for i, w in enumerate(disp):
        if i in anchors: w["start"], w["end"] = float(anchors[i][1]), float(anchors[i][2])
        else: w["start"], w["end"] = float(np.interp(L[i], P, T)), float(np.interp(L[i + 1] - 1, P, T))
    return disp

def word_timings(beats, voices, work):
    cache = os.path.join(work, "timing.json")
    key = hashlib.md5(json.dumps([b["narration"] for b in beats] + [v[2] for v in voices]).encode()).hexdigest()
    if os.path.exists(cache):
        c = json.load(open(cache))
        if c.get("key") == key: return c["beats"], c["sim"]
    res, heard, said = [], [], []
    for b, (a, sr, p) in zip(beats, voices):
        segs, _ = whisper().transcribe(p, word_timestamps=True, language="en", beam_size=5,
                                       condition_on_previous_text=False, initial_prompt=b["narration"].replace("*", ""))
        ww = [(w.word, w.start, w.end) for s in segs for w in s.words]
        heard.append(" ".join(x[0] for x in ww)); said.append(b.get("say") or b["narration"].replace("*", ""))
        res.append(align(display_words(b["narration"]), ww, len(a) / sr))
    sim = difflib.SequenceMatcher(None, norm(" ".join(said)).split(), norm(" ".join(heard)).split()).ratio()
    json.dump({"key": key, "beats": res, "sim": sim, "heard": heard}, open(cache, "w"), indent=1)
    return res, sim

# ------------------------------------------------------------------ timeline
def accent_of(script):
    import engine
    cat = script.get("category") or engine.guess_category(script["topic"])
    return cat, engine.ACCENTS[cat]

def build_timeline(script, voices, words, accent):
    import engine
    beats, T, events = [], 0.0, []
    n = len(script["beats"])
    for i, (b, (a, sr, _), ww) in enumerate(zip(script["beats"], voices, words)):
        dur = len(a) / sr
        gap = b.get("gap", .14 if re.search(r"[.?!:]\**$", b["narration"].strip()) else .07)
        if i == n - 1: gap = max(gap, engine.OUTRO + .12)          # room for the signature closing transition
        frames = int(round((dur + gap) * FPS)); D = frames / FPS
        data = b.get("data", {})
        beat = {"index": i, "visual_type": b["visual_type"], "data": data, "words": ww, "D": D, "T0": T,
                "frames": frames, "narration": b["narration"], "outro": i == n - 1,
                "objects": [dict(o) for o in engine.objects_for(b["visual_type"], data)]}
        beat["chunks"] = engine.caption_chunks(ww)
        beats.append(beat)
        ctx = engine.Ctx(accent, D, ww, T, i)
        if i > 0: events.append((T, "swish"))
        if b["visual_type"] == "reveal": events.append((T, "rise"))
        for t, s in engine.EVENTS[b["visual_type"]](data, ctx):
            if 0 <= t < D: events.append((T + t, s))
        T += D
    events += [(T - engine.OUTRO, "swish"), (T - engine.OUTRO * .4, "chime")]   # brand close: node lights up
    events.sort(); dedup = []
    for t, s in events:
        if dedup and abs(dedup[-1][0] - t) < .09 and s not in ("rise", "chime"): continue
        dedup.append((t, s))
    return beats, T, dedup

# ------------------------------------------------------------------ 3D objects + icons (studio3d.cjs)
def run_studio(jobs_doc, work):
    p = os.path.join(work, "studio_jobs.json"); json.dump(jobs_doc, open(p, "w"))
    subprocess.run(["node", os.path.join(ROOT, "studio3d.cjs"), p], check=True)

def prepare_objects(beats, accent, work):
    import engine
    todo = []; code = hashlib.md5(open(os.path.join(ROOT, "studio3d.cjs"), "rb").read()).hexdigest()[:8]
    for b in beats:
        for o, j in zip(b["objects"], engine.object_jobs(b, accent)):
            h = hashlib.md5((code + json.dumps(j, sort_keys=True)).encode()).hexdigest()[:12]
            d = os.path.join(work, "3d", f"{b['index']:02d}_{o['type']}_{h}"); o["dir"] = d
            if not os.path.exists(os.path.join(d, "done")): todo.append(dict(j, out=d))
    if todo:
        log(f"3D: {len(todo)} objetos, {sum(j['frames'] for j in todo)} fotogramas (Three.js)…")
        run_studio({"objects": todo, "parallel": min(4, os.cpu_count() or 2)}, work)

def prepare_icons(work):
    import engine
    req = sorted(engine.ICON_REQ)
    if not req: return False
    log(f"iconos Lucide: {', '.join(n for n, _ in req)}")
    run_studio({"icons": [{"name": n, "size": s, "stroke": engine.ICON_STROKE, "out": os.path.join(engine.ICON_DIR, f"{n}_{s}.png")} for n, s in req]}, work)
    engine.ICON_REQ.clear(); engine.icon_mask.cache_clear(); return True

# ------------------------------------------------------------------ video
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-maxrate", "22M", "-bufsize", "44M", "-pix_fmt", "yuv420p",
       "-profile:v", "high", "-level", "5.1", "-g", "120", "-bf", "2"]

def _render_scene(job):
    import engine
    beat, accent, seed, path, f0 = job
    bg = engine.Background(accent, seed)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{engine.W}x{engine.H}", "-r", str(FPS),
           "-i", "-"] + ENC + ["-r", str(FPS), path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(beat["frames"]):
        p.stdin.write(np.ascontiguousarray(engine.render_frame(beat, f / FPS, bg, accent, fi=f0 + f)).tobytes())
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError("ffmpeg failed on " + path)
    return path

def render_video(beats, accent, seed, work):
    d = os.path.join(work, "scenes"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    f0 = np.cumsum([0] + [b["frames"] for b in beats])
    jobs = [(b, accent, seed, os.path.join(d, f"{b['index']:02d}_{b['visual_type']}.mp4"), int(f0[i])) for i, b in enumerate(beats)]
    order = sorted(range(len(jobs)), key=lambda i: -beats[i]["frames"])
    with Pool(min(len(jobs), os.cpu_count() or 2)) as pool:
        list(pool.imap_unordered(_render_scene, [jobs[i] for i in order]))
    lst = os.path.join(d, "list.txt")
    open(lst, "w").write("".join(f"file '{j[3]}'\n" for j in jobs))
    out = os.path.join(work, "video.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
    return out

# ------------------------------------------------------------------ review sheets
def contact_sheet(frames, path, cols=3, scale=3):
    from PIL import Image, ImageDraw
    import engine
    w, h = engine.W // scale, engine.H // scale; rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), (0, 0, 0)); d = ImageDraw.Draw(sheet)
    for k, (im, lab) in enumerate(frames):
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(engine.safe_overlay(im).resize((w, h), Image.LANCZOS), (x, y)); d.text((x + 8, y + 6), lab, fill=(255, 255, 0))
    sheet.save(path, quality=90)

def review_sheets(beats, accent, seed, work, tag="review"):
    from PIL import Image
    import engine
    bg = engine.Background(accent, seed)
    d = os.path.join(work, tag); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    frames = []
    for b in beats:
        for fr in (.18, .55, .97):
            t = min(b["D"] - 1 / FPS, b["D"] * fr if fr != .18 else .18)
            frames.append((Image.fromarray(engine.render_frame(b, t, bg, accent)), f"{b['index']} {b['visual_type']} t={t:.2f}"))
    paths = []
    for k in range(0, len(frames), 9):
        p = os.path.join(d, f"sheet_{k // 9 + 1}.jpg"); contact_sheet(frames[k:k + 9], p); paths.append(p)
    return paths

def keyframes(video, beats, work, n=6):
    """Extract n key frames from the final mp4 (spread over the beats) for the designer's eye check."""
    from PIL import Image
    d = os.path.join(work, "keyframes"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    pick = [beats[round(i * (len(beats) - 1) / (n - 1))] for i in range(n)]
    frames = []
    for b in pick:
        t = b["T0"] + b["D"] * .7; p = os.path.join(d, f"{b['index']:02d}.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", p], check=True)
        frames.append((Image.open(p).convert("RGB"), f"{b['index']} {b['visual_type']} @{t:.1f}s"))
    paths = []
    for k in (0, 3):
        p = os.path.join(work, f"keyframes_{k // 3 + 1}.jpg"); contact_sheet(frames[k:k + 3], p, 3, 2); paths.append(p)
    return paths

# ------------------------------------------------------------------ outputs
def write_meta(script, beats, out, total, music_src, cat):
    title = script["title"].strip()
    if "#shorts" not in title.lower(): title += " #shorts"
    if len(title.replace("#shorts", "").strip()) > 60: log("AVISO: título > 60 caracteres")
    open(os.path.join(out, "title.txt"), "w").write(title + "\n")
    desc = script["description"][:2]
    src = "\n".join(f"- {s}" for s in script["sources"])
    tags = script.get("tags", [])
    hashtags = " ".join("#" + re.sub(r"\W", "", t) for t in tags[:3])
    open(os.path.join(out, "description.txt"), "w").write("\n".join(desc) + f"\n\nSources:\n{src}\n\n{hashtags} #shorts\n")
    open(os.path.join(out, "tags.txt"), "w").write(", ".join(tags) + "\n")
    md = [f"# {script['title']}", "", f"**Topic:** {script['topic']}  ", f"**Category:** {cat}  ",
          f"**Voice:** {script.get('voice')} @ {script.get('speed')}  ", f"**Music:** {music_src}  **Length:** {total:.1f}s", "",
          "| # | t | visual | narration |", "|---|---|---|---|"]
    for b in beats: md.append(f"| {b['index'] + 1} | {b['T0']:.1f}s | {b['visual_type']} | {b['narration'].replace('*', '**')} |")
    md += ["", "## Sources", src, ""]
    open(os.path.join(out, "script.md"), "w").write("\n".join(md))

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_name,width,height,r_frame_rate",
                        "-of", "json", path], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)

def write_cover(script, beats, accent, seed, out):
    """Thumbnail with the fixed Quiet Circuit cover layout (engine.cover)."""
    import engine
    from PIL import Image
    cv_ = script.get("cover", {}); cb = beats[cv_.get("beat", next((b["index"] for b in beats if b["objects"]), 0))]
    obj = engine.obj_frame(cb["objects"][0]["dir"], cb["frames"] // 2) if cb["objects"] else None
    first = script["beats"][0]["data"].get("shots", [{}])[0]
    Image.fromarray(engine.cover(cb, obj, engine.Background(accent, seed), accent, cv_.get("big", first.get("big", script["title"])),
                                 cv_.get("small", first.get("small")))).save(os.path.join(out, "thumbnail.jpg"), quality=94)

# ------------------------------------------------------------------ main pipeline
def load_script(topic):
    p = os.path.join(SCRIPTS, slugify(topic) + ".json")
    if not os.path.exists(p): return None, p
    return json.load(open(p, encoding="utf-8")), p

def make(topic, review_only=False, mark=True, cover_only=False):
    import engine, audio
    script, sp = load_script(topic)
    if script is None:
        log(f"FALTA GUION: {sp}\n  -> pide a Claude: 'escribe el guion de \"{topic}\"' (verifica datos y fuentes)."); return None
    slug = slugify(script.get("topic", topic)); work = os.path.join(BUILD, slug); os.makedirs(work, exist_ok=True)
    nwords = sum(len(b["narration"].split()) for b in script["beats"])
    log(f"[{slug}] {len(script['beats'])} beats, {nwords} palabras" + ("" if 90 <= nwords <= 130 else "  (AVISO: fuera de 90–130)"))
    voice, speed = script.get("voice", "af_heart"), script.get("speed", 1.05)
    cat, accent = accent_of(script); seed = int(hashlib.md5(slug.encode()).hexdigest(), 16) % 10000
    log(f"categoría {cat} → acento {accent}")

    log("voz (Kokoro)…"); voices = tts_beats(script["beats"], voice, speed, work)
    log("tiempos por palabra (faster-whisper)…"); words, sim = word_timings(script["beats"], voices, work)
    log(f"   transcripción vs guion: {sim:.0%}" + ("" if sim > .85 else "  (AVISO: revisar pronunciación)"))
    beats, total, events = build_timeline(script, voices, words, accent)
    log(f"   duración {total:.1f}s, {nwords / total * 60:.0f} palabras/min, {len(events)} efectos")
    if not 35 <= total <= 55: log("AVISO: duración fuera de 35–55 s")

    prepare_objects(beats, accent, work)
    if cover_only:
        outs = sorted(d for d in os.listdir(OUTPUT) if d.endswith("_" + slug))
        out = os.path.join(OUTPUT, outs[-1]) if outs else None
        if out: write_cover(script, beats, accent, seed, out); log("portada ->", os.path.join(out, "thumbnail.jpg"))
        return out
    sheets = review_sheets(beats, accent, seed, work)
    if prepare_icons(work): sheets = review_sheets(beats, accent, seed, work)
    log("hojas de revisión:", *sheets)
    if review_only: return work

    log("render de escenas (60 fps)…"); video = render_video(beats, accent, seed, work)
    log("audio (música ambiental + efectos sutiles + ducking)…")
    voice_track = np.zeros(int(total * audio.SR) + audio.SR, np.float32)
    for b, (a, sr, _) in zip(beats, voices):
        v = audio.resample(a, sr); i = int(round(b["T0"] * audio.SR)); voice_track[i:i + len(v)] += v[: len(voice_track) - i]
    voice_track /= np.abs(voice_track).max() + 1e-6
    mixdown, music_src = audio.mix(voice_track * .9, total, events, seed=seed)
    wav = os.path.join(work, "mix.wav"); sf.write(wav, mixdown, audio.SR)

    out = os.path.join(OUTPUT, f"{datetime.date.today().isoformat()}_{slug}")
    shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    mp4 = os.path.join(out, "short.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                    "-t", f"{total:.3f}", "-movflags", "+faststart", mp4], check=True)
    write_cover(script, beats, accent, seed, out)
    write_meta(script, beats, out, total, music_src, cat)
    json.dump(script, open(os.path.join(out, "script.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    info = probe(mp4); size = int(info["format"]["size"]) / 1e6; dur = float(info["format"]["duration"])
    v = next(s for s in info["streams"] if s["codec_name"] == "h264")
    log(f"OK {mp4}: {v['width']}x{v['height']} {v['r_frame_rate']} {dur:.1f}s {size:.1f} MB ({int(info['format']['bit_rate']) / 1e6:.1f} Mb/s)")
    if size > MAX_MB: log("AVISO: pasa de 95 MB")
    log("6 fotogramas clave del mp4:", *keyframes(mp4, beats, work))
    if mark: mark_done(script.get("topic", topic))
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("topic", nargs="?"); ap.add_argument("--batch", type=int, default=0)
    ap.add_argument("--review", action="store_true", help="solo voz + tiempos + hojas de fotogramas")
    ap.add_argument("--no-mark", action="store_true", help="no marcar el tema como done")
    ap.add_argument("--cover-only", action="store_true", help="solo regenerar thumbnail.jpg de un Short ya hecho")
    a = ap.parse_args()
    topics = [a.topic] if a.topic else next_todos(max(1, a.batch))
    if not topics: log("No quedan temas 'todo' en topics.csv -> pide a Claude que añada 20 nuevos."); sys.exit(1)
    missing, made = [], []
    for t in topics:
        r = make(t, review_only=a.review, mark=not (a.no_mark or a.review or a.cover_only), cover_only=a.cover_only)
        (made if r else missing).append(t)
    log(f"hechos: {len(made)}  sin guion: {len(missing)}")
    for t in missing: log("  falta guion:", t)
    sys.exit(0 if not missing else 2)

if __name__ == "__main__":
    main()
