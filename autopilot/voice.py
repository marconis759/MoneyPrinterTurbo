"""Voce narrante naturale con Gemini TTS e allineamento parola per parola.

Gemini legge tutta la clip in una sola richiesta (pochi utilizzi al giorno, adatti al
piano gratuito). Poi faster-whisper, gratuito e locale, trova quando viene detta
ogni parola: da lì si ricavano sottotitoli e cambi di scena. Se qualcosa non va,
render.py ripiega sulla voce Edge.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

import requests

API = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_VOICES = ["Charon", "Orus", "Puck", "Kore", "Aoede", "Fenrir"]
STYLE = ("Leggi questo testo in italiano come il narratore di un documentario sulle fabbriche: "
         "voce calda, umana e sicura, ritmo scorrevole, tono curioso, enfasi sulle parole importanti "
         "e brevi pause naturali tra le frasi. Leggi solo il testo, senza aggiungere nulla:")

_models_cache: list[str] | None = None


def _key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def tts_models(key: str) -> list[str]:
    """Modelli TTS disponibili per questa chiave, dal più adatto al piano gratuito."""
    global _models_cache
    if _models_cache is None:
        names: list[str] = []
        try:
            r = requests.get(f"{API}/models", params={"key": key, "pageSize": 1000}, timeout=30)
            r.raise_for_status()
            for m in r.json().get("models", []):
                if "tts" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", []):
                    names.append(m["name"].split("/", 1)[1])
        except Exception as exc:
            print(f"  Gemini: elenco modelli non disponibile: {exc}")
        rank = {"flash-lite": 1, "flash": 0, "pro": 2}
        names.sort(key=lambda n: (min((v for k, v in rank.items() if k in n), default=3), n))
        _models_cache = names
        print(f"  Gemini TTS disponibili: {names or 'nessuno'}")
    return _models_cache


def gemini_tts(text: str, voice: str, out_wav: Path) -> str | None:
    """Scrive out_wav e restituisce il modello usato, oppure None."""
    key = _key()
    if not key:
        return None
    for model in tts_models(key):
        for voice_config in ({"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}, None):
            body = {"contents": [{"parts": [{"text": f"{STYLE}\n\n{text}"}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"]}}
            if voice_config:
                body["generationConfig"]["speechConfig"] = voice_config
            try:
                r = requests.post(f"{API}/models/{model}:generateContent", params={"key": key},
                                  json=body, timeout=180)
            except requests.RequestException as exc:
                print(f"  Gemini {model}: {exc}")
                break
            if r.status_code == 400 and voice_config:
                continue  # voce non riconosciuta da questo modello: riprova con quella predefinita
            if r.status_code != 200:
                print(f"  Gemini {model}: HTTP {r.status_code} {r.text[:200]}")
                break
            try:
                part = next(p["inlineData"] for p in r.json()["candidates"][0]["content"]["parts"]
                            if "inlineData" in p)
            except (KeyError, IndexError, StopIteration, ValueError):
                print(f"  Gemini {model}: risposta senza audio")
                break
            rate = re.search(r"rate=(\d+)", part.get("mimeType", ""))
            raw = out_wav.with_suffix(".pcm")
            raw.write_bytes(base64.b64decode(part["data"]))
            subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", rate.group(1) if rate else "24000", "-ac", "1",
                            "-i", str(raw), "-af", "apad=pad_dur=0.3", "-ar", "44100", "-ac", "2", str(out_wav)],
                           check=True, capture_output=True)
            return model
    return None


def _norm(token: str) -> str:
    return re.sub(r"[^\w]", "", token.lower())


def transcribe_words(wav: Path) -> list[tuple[str, float, float]] | None:
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:
        print("  faster-whisper non installato: tempi stimati")
        return None
    try:
        model = WhisperModel(os.environ.get("AUTOPILOT_WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
        # L'audio viene decodificato con ffmpeg: evita l'incompatibilità tra faster-whisper e PyAV recenti.
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                             check=True, capture_output=True).stdout
        segments, _ = model.transcribe(np.frombuffer(pcm, dtype=np.float32), language="it", word_timestamps=True)
        return [(w.word.strip(), w.start, w.end) for seg in segments for w in (seg.words or [])]
    except Exception as exc:  # modello non scaricabile o audio illeggibile
        print(f"  faster-whisper non disponibile ({exc.__class__.__name__}: {exc}): tempi stimati")
        return None


def align(scenes: list[str], spoken: list[tuple[str, float, float]] | None, total: float):
    """Restituisce [(parola del copione, inizio, fine, scena)] con i tempi dell'audio."""
    script = [(tok, i) for i, text in enumerate(scenes) for tok in text.split()]
    times: list[tuple[float, float] | None] = [None] * len(script)
    if spoken:
        sm = SequenceMatcher(None, [_norm(t) for t, _ in script], [_norm(w) for w, _, _ in spoken],
                             autojunk=False)
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                times[a + k] = (spoken[b + k][1], spoken[b + k][2])
    if not any(times):  # nessun allineamento: distribuisce in base alla lunghezza delle parole
        weights = [len(t) + 2 for t, _ in script]
        acc, unit = 0.1, (total - 0.4) / max(sum(weights), 1)
        for k, wgt in enumerate(weights):
            times[k] = (acc, acc + wgt * unit)
            acc += wgt * unit
    # Interpola le parole non riconosciute tra le vicine note.
    known = [k for k, t in enumerate(times) if t]
    for k in range(len(times)):
        if times[k]:
            continue
        prev = max((j for j in known if j < k), default=None)
        nxt = min((j for j in known if j > k), default=None)
        start = times[prev][1] if prev is not None else 0.0
        end = times[nxt][0] if nxt is not None else total
        lo = prev if prev is not None else -1
        hi = nxt if nxt is not None else len(times)
        step = (end - start) / (hi - lo - 1)
        times[k] = (start + step * (k - lo - 1), start + step * (k - lo))
    return [(tok, s, e, scene) for (tok, scene), (s, e) in zip(script, times)]
