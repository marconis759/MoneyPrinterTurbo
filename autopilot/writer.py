"""Sceglie i trend del giorno e scrive i piani delle clip con un LLM gratuito.

Fonti dei trend (gratis, senza chiavi): Google Trends RSS e Google News RSS Italia.
LLM: GitHub Models con il GITHUB_TOKEN del workflow (gratis). In alternativa
qualsiasi endpoint compatibile OpenAI tramite LLM_BASE_URL / LLM_API_KEY / LLM_MODEL.
"""
from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from autopilot.render import PALETTES

HEADERS = {"User-Agent": "Mozilla/5.0 (autopilot; +https://github.com)"}
FEEDS = [
    ("google_trends", "https://trends.google.com/trending/rss?geo=IT"),
    ("google_news", "https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it"),
    ("google_news_intrattenimento",
     "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=it&gl=IT&ceid=IT:it"),
    ("google_news_tecnologia",
     "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=it&gl=IT&ceid=IT:it"),
    ("google_news_sport", "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=it&gl=IT&ceid=IT:it"),
]


def fetch_trends(limit_per_feed: int = 20) -> list[dict]:
    items = []
    for name, url in FEEDS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as exc:
            print(f"feed {name} non disponibile: {exc}")
            continue
        for it in root.iter("item"):
            entry = {"source": name, "title": (it.findtext("title") or "").strip()}
            traffic = it.find("{https://trends.google.com/trending/rss}approx_traffic")
            if traffic is not None:
                entry["traffic"] = traffic.text
            news = [n.findtext("{https://trends.google.com/trending/rss}news_item_title")
                    for n in it.findall("{https://trends.google.com/trending/rss}news_item")]
            news = [n for n in news if n]
            if news:
                entry["news"] = news[:3]
            items.append(entry)
            if sum(1 for x in items if x["source"] == name) >= limit_per_feed:
                break
    return items


# ---------------------------------------------------------------------- LLM
def _llm_endpoints() -> list[tuple[str, str, str]]:
    """(base_url, chiave, modello) da provare in ordine."""
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
        raise RuntimeError("Nessuna chiave LLM: imposta GITHUB_TOKEN (Actions) o LLM_BASE_URL + LLM_API_KEY")
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
- Lingua: italiano naturale e parlato, frasi brevi, tono da creator (non da telegiornale).
- Usa SOLO fatti presenti nei titoli forniti o conoscenza generale certa. Mai inventare numeri, date, citazioni.
  Se un dettaglio è incerto, non dirlo.
- Vietato: tragedie o lutti di persone comuni, nomi di indagati o di minori, accuse non provate, consigli medici
  o finanziari, contenuti politici di parte, odio, contenuti sessuali, istigazione a sfide pericolose.
- Ogni clip: 6-7 scene, 28-40 secondi totali (circa 80-110 parole in tutto).
- Scena 1 = gancio fortissimo (domanda, numero, contrasto o "non sapevi che…"), max 12 parole.
- Ultima scena = domanda o call to action che invita a commentare, taggare o salvare.
"""


def pick_topics(trends: list[dict], n: int, avoid: list[str]) -> list[dict]:
    system = ("Sei un social media strategist italiano esperto di TikTok, Reels e Shorts. "
              "Scegli argomenti con il massimo potenziale virale tra quelli di oggi.\n" + RULES)
    user = json.dumps({
        "compito": (f"Scegli {n} argomenti per {n} clip diverse da pubblicare oggi. Privilegia trend in crescita, "
                    "curiosità, intrattenimento, sport, tecnologia, lifestyle e stagionalità. Varia i temi. "
                    "Se le notizie adatte sono poche, completa con curiosità evergreen legate al periodo."),
            "evita_argomenti_gia_fatti": avoid[-80:],
            "trend_di_oggi": trends,
            "formato_risposta": {"topics": [{"id": "slug-breve", "angolo": "taglio della clip in una frase",
                                             "fatti": ["solo fatti certi presi dai titoli"]}]},
    }, ensure_ascii=False)
    return chat_json(system, user, 2500)["topics"][:n]


def write_plan(topic: dict) -> dict:
    system = "Sei un autore di short video virali in italiano.\n" + RULES
    user = json.dumps({
        "argomento": topic,
        "formato_risposta": {
            "id": "slug-breve", "title": "titolo YouTube Shorts max 90 caratteri",
            "caption": "didascalia social max 150 caratteri con 1-2 emoji",
            "hashtags": ["5-7 hashtag, mix di generici (#perte) e specifici"],
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


def generate_plans(n: int, avoid: list[str], out_dir: Path) -> list[Path]:
    trends = fetch_trends()
    print(f"trend raccolti: {len(trends)}")
    if not trends:
        raise RuntimeError("Nessun trend raggiungibile")
    topics = pick_topics(trends, n + 2, avoid)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for topic in topics:
        if len(paths) >= n:
            break
        try:
            plan = validate(write_plan(topic))
        except Exception as exc:
            print(f"piano scartato ({topic.get('id')}): {exc}")
            continue
        plan["trend"] = topic
        path = out_dir / f"{len(paths) + 1:02}-{plan['id']}.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
        print(f"piano: {path.name} — {plan['title']}")
        time.sleep(4)  # resta sotto i limiti gratuiti di GitHub Models
    return paths
