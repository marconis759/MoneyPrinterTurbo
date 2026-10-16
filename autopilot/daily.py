"""Produce il pacchetto del giorno: piani -> video -> manifest.json.

Se esiste autopilot/plans/<data>/ usa quei piani (scritti a mano), altrimenti
li fa scrivere all'LLM partendo dai trend del giorno.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autopilot.render import render_plan  # noqa: E402

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "history.json"
# Orari di pubblicazione (ora italiana): fasce di massimo utilizzo dei social.
SLOTS = ["07:30", "09:00", "11:00", "12:30", "14:00", "16:00", "18:00", "19:30", "21:00", "22:30"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(ZoneInfo("Europe/Rome")).date().isoformat())
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--out", default="dist")
    ap.add_argument("--only", type=int, default=0, help="renderizza solo le prime N (per test)")
    args = ap.parse_args()

    out = Path(args.out) / args.date
    out.mkdir(parents=True, exist_ok=True)
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []

    manual = HERE / "plans" / args.date
    if manual.is_dir():
        plan_paths = sorted(manual.glob("*.json"))[: args.count]
        print(f"uso {len(plan_paths)} piani scritti a mano da {manual}")
    else:
        from autopilot.writer import generate_plans

        avoid = [h["title"] for h in history[-120:]]
        plan_paths = generate_plans(args.count, avoid, out / "plans", args.date)
    if args.only:
        plan_paths = plan_paths[: args.only]

    clips = []
    for i, path in enumerate(plan_paths):
        plan = json.loads(path.read_text(encoding="utf-8"))
        name = f"{i + 1:02}-{plan['id']}.mp4"
        print(f"[{i + 1}/{len(plan_paths)}] {plan['title']}")
        try:
            info = render_plan(plan, out / name, work=out / "work" / plan["id"])
        except Exception as exc:
            print(f"  render fallito: {exc}")
            continue
        clips.append({"file": name, "title": plan["title"], "caption": plan["caption"],
                      "hashtags": plan["hashtags"], "sources": plan.get("sources", []), **info})
    if not clips:
        raise SystemExit("nessuna clip prodotta")
    slots = SLOTS if len(clips) >= len(SLOTS) else SLOTS[:: max(1, len(SLOTS) // len(clips))]
    for clip, slot in zip(clips, slots):
        clip["slot"] = slot
    manifest = {"date": args.date, "clips": clips}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    history += [{"date": args.date, "title": c["title"]} for c in clips]
    HISTORY.write_text(json.dumps(history[-300:], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fatto: {len(clips)} clip in {out}")


if __name__ == "__main__":
    main()
