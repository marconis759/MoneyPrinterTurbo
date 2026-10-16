"""Sceglie gli oggetti del giorno e scrive clip "Come è fatto" con un LLM gratuito.

Formato ispirato ai documentari sulle fabbriche: come nasce un oggetto di tutti i
giorni, passo per passo. I fatti vengono da Wikipedia (gratis, senza chiavi): la
sezione sulla produzione della voce inglese più il riassunto della voce italiana.
LLM: Google Gemini con GEMINI_API_KEY (piano gratuito); in alternativa qualsiasi
endpoint compatibile OpenAI tramite LLM_BASE_URL / LLM_API_KEY / LLM_MODEL.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import date as Date
from pathlib import Path

import requests

from autopilot.render import PALETTES

HEADERS = {"User-Agent": "MoneyPrinterTurbo-autopilot/1.0 (https://github.com/marconis759/MoneyPrinterTurbo)"}

# (nome italiano, voce Wikipedia inglese, voce Wikipedia italiana)
OBJECTS = [
    ("la matita", "Pencil", "Matita"), ("la carta", "Paper", "Carta"), ("il vetro", "Glass", "Vetro"),
    ("le bottiglie di vetro", "Glass bottle", "Bottiglia"), ("il cioccolato", "Chocolate", "Cioccolato"),
    ("la pasta secca", "Pasta", "Pasta (alimento)"), ("il sapone", "Soap", "Sapone"),
    ("il dentifricio", "Toothpaste", "Dentifricio"), ("i jeans", "Jeans", "Jeans"),
    ("le monete", "Coin", "Moneta"), ("la mozzarella", "Mozzarella", "Mozzarella"),
    ("il parmigiano", "Parmigiano Reggiano", "Parmigiano Reggiano"), ("gli pneumatici", "Tire", "Pneumatico"),
    ("le lampadine", "Incandescent light bulb", "Lampada a incandescenza"), ("i pastelli a cera", "Crayon", "Pastello"),
    ("le gomme da masticare", "Chewing gum", "Gomma da masticare"), ("le patatine", "Potato chip", "Patatine fritte in busta"),
    ("i mattoni", "Brick", "Mattone"), ("il cemento", "Cement", "Cemento"), ("l'acciaio", "Steel", "Acciaio"),
    ("le lattine", "Aluminum can", "Lattina"), ("la carta igienica", "Toilet paper", "Carta igienica"),
    ("le candele", "Candle", "Candela"), ("i fiammiferi", "Match", "Fiammifero"), ("le penne a sfera", "Ballpoint pen", "Penna a sfera"),
    ("le palline da tennis", "Tennis ball", "Pallina da tennis"), ("i palloni da calcio", "Ball (association football)", "Pallone da calcio"),
    ("le chitarre", "Guitar", "Chitarra"), ("i pianoforti", "Piano", "Pianoforte"), ("gli specchi", "Mirror", "Specchio"),
    ("le forbici", "Scissors", "Forbici"), ("i coltelli da cucina", "Kitchen knife", "Coltello da cucina"),
    ("le posate", "Cutlery", "Posate"), ("la ceramica", "Porcelain", "Porcellana"), ("i bottoni", "Button", "Bottone"),
    ("le cerniere lampo", "Zipper", "Chiusura lampo"), ("le scarpe da ginnastica", "Sneakers", "Scarpe da ginnastica"),
    ("i fuochi d'artificio", "Fireworks", "Fuochi d'artificio"), ("il pane", "Bread", "Pane"), ("il caffè", "Coffee", "Caffè"),
    ("lo zucchero", "Sugar", "Zucchero"), ("il sale", "Salt", "Sale da cucina"), ("l'olio d'oliva", "Olive oil", "Olio di oliva"),
    ("il gelato", "Ice cream", "Gelato"), ("i marshmallow", "Marshmallow", "Marshmallow"), ("le caramelle gommose", "Gummy candy", "Caramella gommosa"),
    ("i cereali da colazione", "Breakfast cereal", "Cereali per la colazione"), ("il burro", "Butter", "Burro"),
    ("lo yogurt", "Yogurt", "Yogurt"), ("i cornflakes", "Corn flakes", "Corn flakes"), ("il ketchup", "Ketchup", "Ketchup"),
    ("la birra", "Beer", "Birra"), ("il vino", "Wine", "Vino"), ("l'aceto balsamico", "Balsamic vinegar", "Aceto balsamico di Modena"),
    ("i biscotti", "Biscuit", "Biscotto"), ("le bustine di tè", "Tea bag", "Bustina di tè"), ("la plastica", "Plastic", "Materie plastiche"),
    ("le bottiglie di plastica", "Plastic bottle", "Bottiglia di plastica"), ("il nylon", "Nylon", "Nylon"),
    ("i mattoncini da costruzione", "Lego", "Lego"), ("le biglie di vetro", "Marble (toy)", "Biglia"),
    ("i dadi da gioco", "Dice", "Dado (gioco)"), ("le carte da gioco", "Playing card", "Carte da gioco"),
    ("gli occhiali", "Glasses", "Occhiali"), ("le lenti a contatto", "Contact lens", "Lente a contatto"),
    ("gli orologi meccanici", "Mechanical watch", "Orologio meccanico"), ("le batterie", "Battery (electricity)", "Batteria (elettrotecnica)"),
    ("i pannelli solari", "Solar panel", "Pannello fotovoltaico"), ("i chip dei computer", "Integrated circuit", "Circuito integrato"),
    ("la fibra ottica", "Optical fiber", "Fibra ottica"), ("i cavi elettrici", "Electrical cable", "Cavo elettrico"),
    ("le viti", "Screw", "Vite (meccanica)"), ("i chiodi", "Nail (fastener)", "Chiodo"), ("le graffette", "Paper clip", "Fermaglio"),
    ("le puntine", "Thumbtack", "Puntina da disegno"), ("le spille da balia", "Safety pin", "Spilla da balia"),
    ("gli ombrelli", "Umbrella", "Ombrello"), ("le valigie", "Suitcase", "Valigia"), ("i cuscini", "Pillow", "Cuscino"),
    ("i materassi", "Mattress", "Materasso"), ("gli asciugamani", "Towel", "Asciugamano"), ("le spugne", "Sponge (tool)", "Spugna"),
    ("i pennelli", "Paintbrush", "Pennello"), ("la vernice", "Paint", "Vernice"), ("i gessetti", "Chalk", "Gesso"),
    ("le gomme per cancellare", "Eraser", "Gomma per cancellare"), ("il nastro adesivo", "Adhesive tape", "Nastro adesivo"),
    ("la colla", "Adhesive", "Adesivo"), ("le banconote", "Banknote", "Banconota"), ("i francobolli", "Postage stamp", "Francobollo"),
    ("le biciclette", "Bicycle", "Bicicletta"), ("i caschi", "Bicycle helmet", "Casco per bicicletta"), ("gli skateboard", "Skateboard", "Skateboard"),
    ("le tavole da surf", "Surfboard", "Tavola da surf"), ("gli sci", "Ski", "Sci (attrezzo)"), ("le racchette da tennis", "Racket (sports equipment)", "Racchetta"),
    ("le mazze da baseball", "Baseball bat", "Mazza da baseball"), ("le campane", "Bell", "Campana"), ("i violini", "Violin", "Violino"),
    ("i dischi in vinile", "Phonograph record", "Disco in vinile"), ("i profumi", "Perfume", "Profumo"), ("i rossetti", "Lipstick", "Rossetto"),
    ("lo shampoo", "Shampoo", "Shampoo"), ("i cotton fioc", "Cotton swab", "Bastoncino cotonato"), ("gli spazzolini", "Toothbrush", "Spazzolino da denti"),
    ("i cerotti", "Adhesive bandage", "Cerotto"), ("i guanti in lattice", "Medical glove", "Guanto"), ("le mascherine", "Surgical mask", "Mascherina chirurgica"),
    ("i palloncini", "Balloon", "Palloncino"), ("le bolle di sapone", "Soap bubble", "Bolla di sapone"), ("il cartone", "Corrugated fiberboard", "Cartone ondulato"),
    ("le scatolette di tonno", "Canned tuna", "Tonno in scatola"), ("i barattoli di latta", "Tin can", "Scatola di latta"),
]


def _wiki_text(lang: str, title: str) -> str:
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=HEADERS, timeout=30, params={
        "action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki",
        "redirects": 1, "titles": title, "format": "json", "formatversion": 2})
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", [])
    return (pages[0].get("extract") or "") if pages else ""


def _production_part(text: str, limit: int) -> str:
    """Le sezioni che parlano di produzione; altrimenti l'inizio della voce."""
    parts = re.split(r"\n(?===+ )", text)
    keep, level = [], 0
    for part in parts:
        head = re.match(r"(=+) (.*?) =+", part)
        if not head:
            continue
        depth = len(head.group(1))
        if level and depth > level:
            keep.append(part)  # sottosezione della parte sulla produzione
            continue
        level = 0
        if re.search(r"manufactur|production|process|making|fabbricazione|produzione|lavorazione|realizzazione",
                     head.group(2), re.I):
            keep.append(part)
            level = depth
    chosen = "\n".join(keep) if keep else text
    return re.sub(r"\n{2,}", "\n", chosen).strip()[:limit]


def fetch_object_facts(obj: tuple[str, str, str]) -> dict:
    name, en, it = obj
    facts = {"oggetto": name, "fonti": []}
    for lang, title, key, limit in (("en", en, "produzione_en", 3500), ("it", it, "voce_it", 1500)):
        try:
            text = _wiki_text(lang, title)
        except Exception as exc:
            print(f"  Wikipedia {lang} '{title}' non disponibile: {exc}")
            continue
        if text:
            facts[key] = _production_part(text, limit) if lang == "en" else text[:limit]
            facts["fonti"].append(f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}")
    return facts


def choose_objects(n: int, avoid: list[str], day: str) -> list[tuple[str, str, str]]:
    done = " | ".join(avoid).lower()
    fresh = [o for o in OBJECTS if o[0].lower() not in done]
    pool = fresh if len(fresh) >= n else OBJECTS
    rnd = random.Random(day)
    return rnd.sample(pool, min(n, len(pool)))


# ---------------------------------------------------------------------- LLM
_gemini_models: list[str] | None = None


def gemini_text_models(key: str) -> list[str]:
    """I modelli Gemini 'flash' più recenti disponibili per questa chiave (Google ritira spesso i vecchi)."""
    global _gemini_models
    if _gemini_models is None:
        found = []
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                             params={"key": key, "pageSize": 1000}, timeout=30)
            r.raise_for_status()
            for m in r.json().get("models", []):
                name = m["name"].split("/", 1)[1]
                if ("generateContent" not in m.get("supportedGenerationMethods", []) or "flash" not in name
                        or re.search(r"tts|image|live|audio|embed|vision|robotics|computer", name)):
                    continue
                version = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
                found.append((("lite" in name), -float(version.group(1)) if version else 0.0,
                              ("preview" in name or "exp" in name), name))
        except Exception as exc:
            print(f"  Gemini: elenco modelli non disponibile: {exc}")
        _gemini_models = [n for *_, n in sorted(found)][:3] or ["gemini-flash-latest"]
        print(f"  Gemini testo: {_gemini_models}")
    return _gemini_models


def _llm_endpoints() -> list[tuple[str, str, str]]:
    """(base_url, chiave, modello) da provare in ordine."""
    gemini = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini and not os.environ.get("LLM_BASE_URL"):
        base = "https://generativelanguage.googleapis.com/v1beta/openai"
        models = [os.environ["LLM_MODEL"]] if os.environ.get("LLM_MODEL") else gemini_text_models(gemini)
        return [(base, gemini, m) for m in models]
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
- Formato UNICO "Come è fatto": spiega come si fabbrica un oggetto di tutti i giorni, passo per passo,
  dalla materia prima al prodotto finito, come un documentario sulle fabbriche.
- Non citare mai il nome di programmi TV o marchi di terzi nei titoli e nei testi.
- Lingua: italiano naturale e parlato, frasi brevi e concrete, tono curioso da narratore di documentario.
- Usa SOLO fatti presenti negli estratti di Wikipedia forniti o conoscenze tecniche certe e generali.
  Mai inventare numeri, temperature, tempi o nomi di aziende. Se un dettaglio è incerto, non dirlo.
- Ogni clip: 7-8 scene, 30-45 secondi totali (circa 90-120 parole in tutto).
- Scena 1 = gancio fortissimo (es. "Ti sei mai chiesto come nasce…?" o un dato sorprendente), max 12 parole.
- Scene centrali = i passaggi di produzione in ordine, uno per scena, con headline tipo "1. Fusione".
- Ultima scena = domanda o call to action: quale oggetto vuoi vedere nel prossimo video?
- keyword delle scene: 2-3 parole IN INGLESE, semplici e comuni, che si trovano davvero in una
  libreria di video gratuiti: materiale + azione/luogo (es. "molten glass", "steel factory",
  "conveyor belt", "wood cutting", "chocolate factory"). Mai nomi propri o termini troppo tecnici.
"""


def write_plan(facts: dict) -> dict:
    system = "Sei l'autore di brevi video divulgativi 'Come è fatto' per TikTok, Reels e Shorts.\n" + RULES
    user = json.dumps({
        "oggetto": facts["oggetto"], "estratti_wikipedia": facts,
        "formato_risposta": {
            "id": "slug-breve", "title": "titolo max 90 caratteri, es. 'Come è fatta la matita, passo per passo'",
            "caption": "didascalia social max 150 caratteri con 1-2 emoji",
            "hashtags": ["5-7 hashtag, es. #comeèfatto #fabbrica #lososapevi #curiosità #perte + specifici"],
            "palette": "una tra: " + ", ".join(PALETTES),
            "scenes": [{"text": "frase parlata (1-2 frasi)", "headline": "testo a schermo, MAX 4 parole",
                        "keyword": "inquadratura stock IN INGLESE"}],
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


def fallback_plan(facts: dict) -> dict | None:
    """Senza LLM: le prime frasi della voce italiana di Wikipedia, lette come sono."""
    text = re.sub(r"\s+", " ", facts.get("voce_it", "")).strip()
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if len(x.split()) >= 5][:5]
    if len(sentences) < 3:
        return None
    name = facts["oggetto"]
    scenes = [{"text": f"Ti sei mai chiesto da dove vengono {name}? Ecco cosa c'è da sapere.",
               "headline": f"Come è fatto: {name.split(' ', 1)[-1]}", "keyword": "factory production line"}]
    scenes += [{"text": _short(x, 26), "headline": f"{i}.", "keyword": "factory machine"}
               for i, x in enumerate(sentences, 1)]
    scenes.append({"text": "Quale oggetto vuoi vedere nel prossimo video? Scrivilo nei commenti.",
                   "headline": "Il prossimo?", "keyword": "industrial workers"})
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return {"id": f"come-e-fatto-{slug}"[:40], "title": f"Come è fatto: {name}",
            "caption": f"Da dove vengono {name}? 🏭", "scenes": scenes,
            "hashtags": ["#comeèfatto", "#fabbrica", "#lososapevi", "#curiosità", "#perte"],
            "sources": facts["fonti"]}


def generate_plans(n: int, avoid: list[str], out_dir: Path, day: str = "") -> list[Path]:
    day = day or Date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    llm_ok = True
    for obj in choose_objects(n + 3, avoid, day):
        if len(paths) >= n:
            break
        facts = fetch_object_facts(obj)
        if not facts.get("produzione_en") and not facts.get("voce_it"):
            continue
        plan = None
        if llm_ok:
            try:
                plan = validate(write_plan(facts))
                plan["sources"] = facts["fonti"]
                time.sleep(4)  # resta sotto i limiti gratuiti dei provider
            except RuntimeError as exc:
                print(f"LLM non disponibile ({exc}): uso i riassunti di Wikipedia")
                llm_ok = False
            except Exception as exc:
                print(f"piano scartato ({obj[0]}): {exc}")
                continue
        if plan is None and not llm_ok:
            plan = fallback_plan(facts)
            if plan:
                plan = validate(plan)
        if not plan:
            continue
        plan["oggetto"] = obj[0]
        path = out_dir / f"{len(paths) + 1:02}-{plan['id']}.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
        print(f"piano: {path.name} — {plan['title']}")
    return paths
