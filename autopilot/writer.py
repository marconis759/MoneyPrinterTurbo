"""Sceglie le curiosità storiche del giorno e scrive i piani delle clip con un LLM gratuito.

Fonte dei fatti (gratis, senza chiavi): gli eventi "accadde oggi" di Wikipedia.
LLM: Google Gemini con GEMINI_API_KEY (piano gratuito); in alternativa qualsiasi
endpoint compatibile OpenAI tramite LLM_BASE_URL / LLM_API_KEY / LLM_MODEL.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date as Date
from pathlib import Path

import requests

from autopilot.render import PALETTES

HEADERS = {"User-Agent": "MoneyPrinterTurbo-autopilot/1.0 (https://github.com/marconis759/MoneyPrinterTurbo)"}


def fetch_history(day: str) -> list[dict]:
    """Eventi di questo giorno nella storia, con un estratto della voce Wikipedia come base dei fatti."""
    d = Date.fromisoformat(day)
    for lang in ("it", "en"):
        url = f"https://api.wikimedia.org/feed/v1/wikipedia/{lang}/onthisday/all/{d.month:02}/{d.day:02}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"Wikipedia ({lang}) non disponibile: {exc}")
            continue
        events = []
        for kind in ("selected", "events", "births"):
            for ev in data.get(kind, []):
                pages = ev.get("pages") or []
                events.append({
                    "lingua": lang, "tipo": kind, "anno": ev.get("year"), "evento": ev.get("text", ""),
                    "voci": [{"titolo": p.get("normalizedtitle") or p.get("title"),
                              "estratto": (p.get("extract") or "")[:700]} for p in pages[:2]],
                })
        if events:
            return events
    return []


# ---------------------------------------------------------------------- LLM
def _llm_endpoints() -> list[tuple[str, str, str]]:
    """(base_url, chiave, modello) da provare in ordine."""
    gemini = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini and not os.environ.get("LLM_BASE_URL"):
        return [("https://generativelanguage.googleapis.com/v1beta/openai", gemini,
                 os.environ.get("LLM_MODEL") or "gemini-2.5-flash")]
    if os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_API_KEY"):
        return [(os.environ["LLM_BASE_URL"].rstrip("/"), os.environ["LLM_API_KEY"],
                 os.environ.get("LLM_MODEL") or "gpt-4o-mini")]
    token = os.environ.get("GITHUB_TOKEN", "")
    custom = os.environ.get("LLM_MODEL")
    endpoints = [("https://models.github.ai/inference", token, custom or "openai/gpt-4.1-mini"),
                 ("https://models.github.ai/inference", token, "openai/gpt-4o-mini")]
    return [e for e in endpoints if e[1]]


def chat_json(system: str, user: str, max_tokens: int = 3000) -> dict:
    endpoints = _llm_endpoints()
    if not endpoints:
        raise RuntimeError("Nessuna chiave LLM: imposta GEMINI_API_KEY (o LLM_BASE_URL + LLM_API_KEY)")
    errors = []
    for base, key, model in endpoints:
        body = {
            "model": model, "temperature": 0.8, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        for attempt in range(4):
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                if "models.github.ai" in base:
                    headers.update({"Accept": "application/vnd.github+json",
                                    "X-GitHub-Api-Version": "2026-03-10"})
                r = requests.post(f"{base}/chat/completions", json=body, timeout=180, allow_redirects=False,
                                  headers=headers)
            except requests.RequestException as exc:
                errors.append(f"{base} {model}: {exc}")
                time.sleep(5)
                continue
            if r.status_code == 400 and "response_format" in body and "response_format" in r.text:
                body.pop("response_format")  # modello senza modalità JSON: il prompt chiede comunque JSON
                continue
            if r.status_code == 429 or r.status_code >= 500:
                errors.append(f"{base} {model}: HTTP {r.status_code} {r.text[:200]}")
                time.sleep(min(60, 15 * (attempt + 1)))
                continue
            try:
                text = r.json()["choices"][0]["message"]["content"]
                text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
                return json.loads(text)
            except (ValueError, KeyError, IndexError, TypeError):
                errors.append(f"{base} {model}: HTTP {r.status_code} risposta non valida: {r.text[:300]!r}")
                break  # passa al prossimo endpoint
    for e in errors:
        print("  LLM:", e)
    raise RuntimeError("Nessun endpoint LLM ha risposto correttamente")


RULES = """Regole editoriali (obbligatorie):
- Tema UNICO: curiosità sulla storia (eventi, invenzioni, personaggi, usanze, record, aneddoti).
- Lingua: italiano naturale e parlato, frasi brevi, tono da creator appassionato (non da libro di scuola).
- Usa SOLO fatti presenti negli eventi ed estratti forniti, oppure fatti storici notissimi e certi.
  Mai inventare date, numeri, nomi o citazioni. Se un dettaglio è incerto, non dirlo.
- Tratta guerre, stragi e tragedie con rispetto: niente toni da spettacolo, meglio evitarle se non c'è
  un aneddoto adatto. Niente politica di parte, odio, contenuti sessuali o macabri.
- Ogni clip: 6-7 scene, 28-40 secondi totali (circa 80-110 parole in tutto).
- Scena 1 = gancio fortissimo (domanda, numero, contrasto o "non sapevi che…"), max 12 parole.
- Ultima scena = domanda o call to action che invita a commentare, taggare o salvare.
"""


def pick_topics(events: list[dict], n: int, avoid: list[str], day: str) -> list[dict]:
    system = ("Sei un autore italiano di short video di divulgazione storica per TikTok, Reels e Shorts. "
              "Scegli le storie con il massimo potenziale virale: sorprendenti, curiose, facili da raccontare.\n"
              + RULES)
    user = json.dumps({
        "compito": (f"Scegli {n} curiosità storiche per {n} clip diverse da pubblicare il {day}. "
                    "Preferisci gli eventi di questo giorno (angolo 'accadde oggi'); se non bastano, aggiungi "
                    "curiosità storiche notissime e certe. Varia epoche e luoghi, includi storia italiana."),
        "evita_argomenti_gia_fatti": avoid[-120:],
        "eventi_di_oggi_da_wikipedia": events[:60],
        "formato_risposta": {"topics": [{"id": "slug-breve", "angolo": "taglio della clip in una frase",
                                         "anno": "anno se noto", "fatti": ["solo fatti certi, presi dagli estratti"]}]},
    }, ensure_ascii=False)
    return chat_json(system, user, 3000)["topics"][:n]


def write_plan(topic: dict) -> dict:
    system = "Sei un autore di short video virali di curiosità storiche in italiano.\n" + RULES
    user = json.dumps({
        "argomento": topic,
        "formato_risposta": {
            "id": "slug-breve", "title": "titolo YouTube Shorts max 90 caratteri",
            "caption": "didascalia social max 150 caratteri con 1-2 emoji",
            "hashtags": ["5-7 hashtag, mix di generici (#storia #lososapevi #perte) e specifici"],
            "palette": "una tra: " + ", ".join(PALETTES),
            "scenes": [{"text": "frase parlata (1-2 frasi)",
                        "headline": "testo a schermo, MAX 4 parole",
                        "keyword": "2-3 parole IN INGLESE per cercare un video stock adatto (no nomi propri)"}],
        },
    }, ensure_ascii=False)
    return chat_json(system, user, 2500)


def validate(plan: dict) -> dict:
    scenes = [s for s in plan.get("scenes", []) if str(s.get("text", "")).strip()]
    if not 3 <= len(scenes) <= 9:
        raise ValueError(f"numero di scene non valido: {len(scenes)}")
    words = sum(len(s["text"].split()) for s in scenes)
    if not 50 <= words <= 160:
        raise ValueError(f"lunghezza testo non valida: {words} parole")
    plan["id"] = re.sub(r"[^a-z0-9-]+", "-", str(plan.get("id", "clip")).lower()).strip("-")[:40] or "clip"
    plan["title"] = str(plan.get("title", ""))[:95]
    plan["caption"] = str(plan.get("caption", ""))[:300]
    plan["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in plan.get("hashtags", [])][:8]
    for s in scenes:
        s["headline"] = " ".join(str(s.get("headline", "")).split()[:6])
        s["keyword"] = str(s.get("keyword", ""))[:60]
    plan["scenes"] = scenes
    return plan


def _short(text: str, words: int) -> str:
    parts = (text or "").split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]


def fallback_plans(events: list[dict], day: str) -> list[dict]:
    """Senza LLM: 'accadde oggi' con gli eventi di Wikipedia in italiano, letti come sono."""
    d = Date.fromisoformat(day)
    when = f"{d.day} {MESI[d.month - 1]}"
    items = [e for e in events if e["lingua"] == "it" and e["tipo"] in ("selected", "events")
             and e.get("anno") and e.get("evento")]
    items = sorted(items, key=lambda e: e["anno"])
    plans = []
    for part, chunk in enumerate((items[:5], items[5:10]), 1):
        if len(chunk) < 3:
            continue
        scenes = [{"text": f"Cosa è successo il {when} nella storia? Ecco {len(chunk)} date da ricordare.",
                   "headline": f"Accadde il {when}", "keyword": "old history book"}]
        for e in chunk:
            scenes.append({"text": f"Nel {e['anno']}: {_short(e['evento'], 24)}",
                           "headline": str(e["anno"]), "keyword": "vintage archive"})
        scenes.append({"text": "Quale di queste non conoscevi? Scrivilo nei commenti e salva il video.",
                       "headline": "Tu lo sapevi?", "keyword": "museum visitors"})
        plans.append({
            "id": f"accadde-oggi-{part}", "title": f"Accadde oggi, {when}: {len(chunk)} date che hanno fatto la storia",
            "caption": f"Accadde il {when} 📜 Quale non conoscevi?",
            "hashtags": ["#accaddeoggi", "#storia", "#lososapevi", "#curiosità", "#perte"],
            "scenes": scenes, "sources": [f"https://it.wikipedia.org/wiki/{d.day}_{MESI[d.month - 1]}"],
        })
    return plans


def generate_plans(n: int, avoid: list[str], out_dir: Path, day: str = "") -> list[Path]:
    day = day or Date.today().isoformat()
    events = fetch_history(day)
    print(f"eventi storici raccolti: {len(events)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    def save(plan: dict) -> None:
        path = out_dir / f"{len(paths) + 1:02}-{plan['id']}.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
        print(f"piano: {path.name} — {plan['title']}")

    try:
        topics = pick_topics(events, n + 2, avoid, day)
    except Exception as exc:
        print(f"LLM non disponibile ({exc}): uso 'accadde oggi' di Wikipedia")
        for plan in fallback_plans(events, day):
            save(plan)
        return paths
    for topic in topics:
        if len(paths) >= n:
            break
        try:
            plan = validate(write_plan(topic))
        except Exception as exc:
            print(f"piano scartato ({topic.get('id')}): {exc}")
            continue
        plan["trend"] = topic
        save(plan)
        time.sleep(4)  # resta sotto i limiti gratuiti dei provider
    return paths
