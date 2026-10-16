"""Trasforma un piano JSON in una clip verticale 1080x1920 pronta per i social.

Ogni scena del piano ha: testo parlato, titolo a schermo e una parola chiave in
inglese per lo sfondo. La voce usa Edge TTS (gratis, nessuna chiave); se Edge
non è raggiungibile ripiega su pico2wave offline. Lo sfondo usa Pexels quando
c'è PEXELS_API_KEY, altrimenti un gradiente animato generato da ffmpeg.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
SONGS = ROOT / "resource" / "songs"
W, H, FPS = 1080, 1920, 30

VOICES = ["it-IT-DiegoNeural", "it-IT-ElsaNeural", "it-IT-IsabellaNeural", "it-IT-GiuseppeMultilingualNeural"]

PALETTES = {
    "violet": ("0x12062a", "0x5a0f7a", "0xc04bff", "#FFE45C"),
    "teal": ("0x02161c", "0x00585e", "0x2fe0c0", "#7CFFB2"),
    "red": ("0x1c0004", "0x6e0a14", "0xff3b4e", "#FFD166"),
    "gold": ("0x1a1000", "0x6b3d00", "0xffb020", "#FFE45C"),
    "blue": ("0x020a24", "0x0b2f7a", "0x3d8bff", "#9BE7FF"),
    "green": ("0x041a08", "0x0e5a24", "0x3ddc68", "#E6FF6B"),
    "pink": ("0x22041a", "0x7a0f55", "0xff4fb0", "#FFE45C"),
    "orange": ("0x1e0800", "0x7a2a00", "0xff7a1a", "#FFF06B"),
}


@dataclass
class Word:
    text: str
    start: float
    end: float


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


# --------------------------------------------------------------------- voce
async def _edge_tts(text: str, voice: str, rate: str, out: Path) -> list[Word]:
    import edge_tts

    words: list[Word] = []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(out, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append(Word(chunk["text"], start, start + chunk["duration"] / 1e7))
    return words


def _pico_tts(text: str, out: Path) -> list[Word]:
    raw = out.with_suffix(".raw.wav")
    run(["pico2wave", "-l", "it-IT", "-w", str(raw), text])
    run(["ffmpeg", "-y", "-i", str(raw), "-af", "atempo=1.12", str(out)])
    dur = probe_duration(out)
    tokens = text.split()
    total = sum(len(t) + 2 for t in tokens) or 1
    words, t = [], 0.1
    for tok in tokens:
        d = (dur - 0.2) * (len(tok) + 2) / total
        words.append(Word(tok, t, t + d))
        t += d
    return words


def synthesize(text: str, voice: str, out: Path) -> tuple[list[Word], str]:
    """Restituisce le parole con i tempi e il motore usato."""
    if os.environ.get("AUTOPILOT_TTS", "edge") == "edge":
        for _ in range(3):
            try:
                words = asyncio.run(_edge_tts(text, voice, "+10%", out))
                if words and out.stat().st_size > 1000:
                    return words, "edge"
            except Exception as exc:  # rete assente o servizio occupato
                print(f"  edge-tts non disponibile: {exc}")
    if shutil.which("pico2wave"):
        return _pico_tts(text, out), "pico"
    raise RuntimeError("Nessun motore TTS disponibile (edge-tts o pico2wave)")


# ------------------------------------------------------------------ sfondi
def pexels_video(query: str, min_dur: float, used: set[int], cache: Path) -> Path | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not query:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15},
            headers={"Authorization": key}, timeout=20,
        )
        r.raise_for_status()
        for video in r.json().get("videos", []):
            if video["id"] in used or video.get("duration", 0) < min(min_dur, 4):
                continue
            files = [f for f in video["video_files"]
                     if f.get("width") and f.get("height") and f["height"] > f["width"] and f["height"] >= 1280]
            if not files:
                continue
            best = min(files, key=lambda f: abs(f["height"] - 1920))
            used.add(video["id"])
            target = cache / f"pexels-{video['id']}.mp4"
            if not target.exists():
                with requests.get(best["link"], stream=True, timeout=60) as dl:
                    dl.raise_for_status()
                    with open(target, "wb") as fh:
                        for part in dl.iter_content(1 << 20):
                            fh.write(part)
            return target
    except Exception as exc:
        print(f"  Pexels non disponibile per '{query}': {exc}")
    return None


def headline_png(text: str, accent: str, out: Path, hook: bool) -> None:
    img = Image.new("RGBA", (W, 760), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    words = text.upper().split()
    size = 150 if hook else 120
    while True:
        font = ImageFont.truetype(str(FONT), size)
        lines, cur = [], ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if d.textlength(cand, font=font) <= 960 or not cur:
                cur = cand
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        widest = max(d.textlength(line, font=font) for line in lines)
        if (len(lines) <= 3 and widest <= 980) or size <= 60:
            break
        size -= 8
    line_h = int(size * 1.12)
    y = (760 - line_h * len(lines)) // 2
    for i, line in enumerate(lines):
        fill = accent if i == 0 else "#FFFFFF"
        tw = d.textlength(line, font=font)
        d.text(((W - tw) / 2, y), line, font=font, fill=fill,
               stroke_width=max(6, size // 14), stroke_fill="#000000")
        y += line_h
    img.save(out)


def scene_clip(bg: Path | None, palette: str, png: Path, dur: float, out: Path, seed: int) -> None:
    c0, c1, c2, _ = PALETTES.get(palette, PALETTES["violet"])
    if bg:
        inputs = ["-stream_loop", "-1", "-i", str(bg)]
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
                f"eq=brightness=-0.10:saturation=1.15,drawbox=c=black@0.30:t=fill,setsar=1[bg]")
    else:
        rnd = random.Random(seed)
        inputs = ["-f", "lavfi", "-i",
                  f"gradients=s={W}x{H}:c0={c0}:c1={c1}:c2={c2}:c3={c0}:nb_colors=4:"
                  f"speed={rnd.uniform(0.008, 0.02):.4f}:seed={seed}:rate={FPS}:d={dur:.2f}"]
        base = "[0:v]noise=alls=6:allf=t,setsar=1[bg]"
    fc = (f"{base};[1:v]format=rgba,fade=in:st=0:d=0.25:alpha=1[hl];"
          f"[bg][hl]overlay=x=0:y='330+60*max(0\\,1-t/0.25)':shortest=0[v]")
    run(["ffmpeg", "-y", *inputs, "-loop", "1", "-i", str(png), "-filter_complex", fc,
         "-map", "[v]", "-t", f"{dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(out)])


# --------------------------------------------------------------- sottotitoli
def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def write_ass(words: list[Word], accent: str, out: Path) -> None:
    r, g, b = accent[1:3], accent[3:5], accent[5:7]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Be Vietnam Pro,150,&H00{b}{g}{r},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,9,3,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines, chunk = [], []

    def flush(next_start: float | None):
        if not chunk:
            return
        start = chunk[0].start
        end = chunk[-1].end + 0.12
        if next_start is not None:
            end = min(end, next_start)
        text = " ".join(w.text for w in chunk).upper().replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,"
                     f"{{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}}{text}")
        chunk.clear()

    for i, w in enumerate(words):
        chunk.append(w)
        n_chars = sum(len(x.text) for x in chunk)
        ends_sentence = bool(re.search(r"[.!?…:;,]$", w.text))
        if len(chunk) >= 3 or n_chars >= 16 or ends_sentence:
            flush(words[i + 1].start if i + 1 < len(words) else None)
    flush(None)
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------- render
def render_plan(plan: dict, out_file: Path, work: Path | None = None, seed: int | None = None) -> dict:
    seed = seed if seed is not None else int(hashlib.md5(plan["id"].encode()).hexdigest()[:8], 16)
    rnd = random.Random(seed)
    palette = plan.get("palette") if plan.get("palette") in PALETTES else rnd.choice(list(PALETTES))
    accent = PALETTES[palette][3]
    voice = plan.get("voice") if plan.get("voice") in VOICES else rnd.choice(VOICES)
    work = Path(work or tempfile.mkdtemp(prefix="autopilot-"))
    work.mkdir(parents=True, exist_ok=True)
    cache = work / "cache"
    cache.mkdir(exist_ok=True)

    all_words: list[Word] = []
    segments, audios, t0, used, engines, backgrounds = [], [], 0.0, set(), set(), 0
    for i, scene in enumerate(plan["scenes"]):
        audio = work / f"s{i:02}.mp3"
        words, engine = synthesize(scene["text"], voice, audio)
        engines.add(engine)
        wav = work / f"s{i:02}.wav"
        run(["ffmpeg", "-y", "-i", str(audio), "-af", "apad=pad_dur=0.18", "-ar", "44100", "-ac", "2", str(wav)])
        dur = probe_duration(wav)
        all_words += [Word(w.text, w.start + t0, w.end + t0) for w in words]
        png = work / f"h{i:02}.png"
        headline_png(scene.get("headline") or "", accent, png, hook=(i == 0))
        bg = pexels_video(scene.get("keyword", ""), dur, used, cache)
        backgrounds += bool(bg)
        seg = work / f"v{i:02}.mp4"
        scene_clip(bg, palette, png, dur, seg, seed + i)
        segments.append(seg)
        audios.append(wav)
        t0 += dur

    concat_v = work / "concat_v.txt"
    concat_v.write_text("".join(f"file '{p}'\n" for p in segments))
    concat_a = work / "concat_a.txt"
    concat_a.write_text("".join(f"file '{p}'\n" for p in audios))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_v), "-c", "copy", str(work / "video.mp4")])
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_a), str(work / "voice.wav")])

    ass = work / "captions.ass"
    write_ass(all_words, accent, ass)
    songs = sorted(SONGS.glob("*.mp3"))
    song = songs[seed % len(songs)]
    total = t0
    fonts_dir = str(FONT.parent)
    vf = (f"[0:v]drawbox=x=0:y=0:w='iw*t/{total:.3f}':h=14:c={accent}@0.95:t=fill,"
          f"subtitles='{ass}':fontsdir='{fonts_dir}'[v]")
    af = ("[2:a]volume=0.10,afade=t=in:d=1[bgm];"
          f"[1:a][bgm]amix=inputs=2:duration=first:dropout_transition=0,afade=t=out:st={max(total - 0.6, 0):.2f}:d=0.6,"
          "loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(work / "video.mp4"), "-i", str(work / "voice.wav"),
         "-stream_loop", "-1", "-i", str(song), "-filter_complex", f"{vf};{af}",
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium",
         "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
         "-movflags", "+faststart", str(out_file)])
    return {"duration": round(total, 2), "voice": voice if "edge" in engines else "pico2wave",
            "palette": palette, "pexels_backgrounds": backgrounds, "scenes": len(segments)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Renderizza un piano JSON in un video")
    ap.add_argument("plan")
    ap.add_argument("out")
    args = ap.parse_args()
    info = render_plan(json.loads(Path(args.plan).read_text(encoding="utf-8")), Path(args.out))
    print(json.dumps(info, ensure_ascii=False))
