"""Pubblica la prossima clip in calendario sui canali configurati.

Ogni canale si attiva solo se i suoi secret sono presenti:
  Telegram  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID       (ti manda il video sul telefono)
  YouTube   YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  Instagram IG_USER_ID, IG_ACCESS_TOKEN                 (Reels, API ufficiale gratuita)
  Upload-Post UPLOAD_POST_API_KEY, UPLOAD_POST_USER     (TikTok; piano gratis 10 upload/mese)
Lo stato (cosa è già uscito) sta in published.json accanto al manifest.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Europe/Rome")


def full_caption(clip: dict) -> str:
    return f"{clip['caption']}\n\n{' '.join(clip['hashtags'])}".strip()


# ------------------------------------------------------------------ canali
def telegram(clip: dict, video: Path) -> str:
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    text = f"🎬 {clip['title']}\n\n{full_caption(clip)}"[:1024]
    with open(video, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                          data={"chat_id": chat, "caption": text, "supports_streaming": "true"},
                          files={"video": fh}, timeout=300)
    r.raise_for_status()
    return "inviato"


def youtube(clip: dict, video: Path) -> str:
    tok = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30)
    tok.raise_for_status()
    access = tok.json()["access_token"]
    title = clip["title"][:92]
    if "#shorts" not in title.lower():
        title = f"{title} #shorts"[:100]
    meta = {
        "snippet": {"title": title, "description": full_caption(clip), "categoryId": "24",
                    "tags": [h.lstrip("#") for h in clip["hashtags"]], "defaultLanguage": "it"},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"),
                   "selfDeclaredMadeForKids": False},
    }
    size = video.stat().st_size
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        data=json.dumps(meta), timeout=60)
    init.raise_for_status()
    with open(video, "rb") as fh:
        up = requests.put(init.headers["Location"], data=fh, timeout=600,
                          headers={"Authorization": f"Bearer {access}", "Content-Type": "video/mp4"})
    up.raise_for_status()
    return f"https://youtube.com/shorts/{up.json()['id']}"


def instagram(clip: dict, video: Path, video_url: str) -> str:
    uid, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    api = "https://graph.instagram.com/v21.0"
    c = requests.post(f"{api}/{uid}/media", data={
        "media_type": "REELS", "video_url": video_url, "caption": full_caption(clip)[:2200],
        "share_to_feed": "true", "access_token": token}, timeout=60)
    c.raise_for_status()
    cid = c.json()["id"]
    for _ in range(60):
        s = requests.get(f"{api}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=30)
        status = s.json().get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram ha rifiutato il video: {s.text[:300]}")
        time.sleep(10)
    p = requests.post(f"{api}/{uid}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60)
    p.raise_for_status()
    # Prolunga la validità del token (60 giorni da ora) finché il sistema gira.
    requests.get("https://graph.instagram.com/refresh_access_token",
                 params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    return f"media {p.json().get('id')}"


def upload_post(clip: dict, video: Path) -> str:
    platforms = os.environ.get("UPLOAD_POST_PLATFORMS", "tiktok").split(",")
    data = [("user", os.environ["UPLOAD_POST_USER"]), ("title", full_caption(clip)[:2200]),
            ("privacy_level", "PUBLIC_TO_EVERYONE")]
    data += [("platform[]", p.strip()) for p in platforms if p.strip()]
    with open(video, "rb") as fh:
        r = requests.post("https://api.upload-post.com/api/upload", data=data, files={"video": fh},
                          headers={"Authorization": f"Apikey {os.environ['UPLOAD_POST_API_KEY']}"}, timeout=300)
    r.raise_for_status()
    return "inviato"


CHANNELS = {
    "telegram": (("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"), telegram),
    "youtube": (("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"), youtube),
    "instagram": (("IG_USER_ID", "IG_ACCESS_TOKEN"), instagram),
    "upload_post": (("UPLOAD_POST_API_KEY", "UPLOAD_POST_USER"), upload_post),
}


def enabled_channels() -> list[str]:
    skip = {c.strip() for c in os.environ.get("AUTOPILOT_SKIP_CHANNELS", "").split(",") if c.strip()}
    return [name for name, (keys, _) in CHANNELS.items()
            if name not in skip and all(os.environ.get(k) for k in keys)]


# --------------------------------------------------------------- calendario
def slot_time(manifest: dict, clip: dict) -> datetime:
    return datetime.fromisoformat(f"{manifest['date']}T{clip['slot']}:00").replace(tzinfo=TZ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="cartella con manifest.json e i video")
    ap.add_argument("--base-url", default="", help="URL pubblico dei video (per Instagram)")
    ap.add_argument("--force-next", action="store_true", help="pubblica la prossima anche se non è l'ora")
    args = ap.parse_args()

    folder = Path(args.folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    state_file = folder / "published.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {"published": []}
    done = {p["file"] for p in state["published"]}
    assets_file = folder / "assets.txt"
    available = set(assets_file.read_text().split()) if assets_file.exists() else None
    # Una clip cancellata dalla Release viene saltata.
    pending = [c for c in manifest["clips"]
               if c["file"] not in done and (available is None or c["file"] in available)]
    channels = enabled_channels()
    print(f"canali attivi: {channels or 'nessuno'} — pubblicate {len(done)}, in coda {len(pending)}")
    if not pending:
        print("tutte le clip di oggi sono uscite")
        return
    if slot_time(manifest, pending[0]) > datetime.now(TZ) and not args.force_next:
        print(f"prossima clip alle {pending[0]['slot']}: niente da fare adesso")
        return
    clip = pending[0]
    video = folder / clip["file"]
    results = {}
    for name in channels:
        fn = CHANNELS[name][1]
        try:
            if name == "instagram":
                if not args.base_url:
                    raise RuntimeError("serve --base-url pubblico per Instagram")
                results[name] = fn(clip, video, f"{args.base_url.rstrip('/')}/{clip['file']}")
            else:
                results[name] = fn(clip, video)
        except Exception as exc:
            results[name] = f"ERRORE: {exc}"[:500]
        print(f"  {name}: {results[name]}")
    if channels and all(str(v).startswith("ERRORE") for v in results.values()):
        # Non segna la clip come uscita: il prossimo giro riprova.
        raise SystemExit("tutti i canali hanno fallito")
    state["published"].append({"file": clip["file"], "at": datetime.now(TZ).isoformat(timespec="minutes"),
                                "results": results})
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
