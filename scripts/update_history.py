#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")

PUBLIC_FIELDS = [
    "source_channel",
    "post_id",
    "date",
    "link",
    "residential_complexes",
    "developers",
    "stage",
    "categories",
    "defect_counts",
    "distinctive_details",
]


def key(item: dict) -> str:
    return f"{item.get('source_channel','')}::{item.get('post_id','')}::{item.get('link','')}"


def slim(item: dict) -> dict:
    out = {field: item.get(field) for field in PUBLIC_FIELDS}
    # Keep only case-specific short details. No raw post text, no HTML, no media.
    if out.get("distinctive_details"):
        out["distinctive_details"] = [str(x)[:280] for x in out["distinctive_details"][:5]]
    return out


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", default="data/latest.min.json")
    ap.add_argument("--history", default="data/signals.min.jsonl")
    ap.add_argument("--snapshots", default="data/snapshots")
    ap.add_argument("--now")
    args = ap.parse_args()

    latest_path = Path(args.latest)
    history_path = Path(args.history)
    snapshots_dir = Path(args.snapshots)
    generated_at = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest_items = [slim(item) for item in latest.get("items", [])]
    existing = read_jsonl(history_path)

    merged = {key(item): item for item in existing if key(item).strip(":")}
    for item in latest_items:
        merged[key(item)] = item
    rows = sorted(merged.values(), key=lambda x: (x.get("date") or "", x.get("source_channel") or "", x.get("post_id") or ""), reverse=True)
    write_jsonl(history_path, rows)

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    day = generated_at.astimezone(MOSCOW).strftime("%Y-%m-%d")
    snapshot = {
        "generated_at": generated_at.isoformat(),
        "items": latest_items,
    }
    with gzip.open(snapshots_dir / f"{day}.min.json.gz", "wt", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, sort_keys=True)

    print(f"history_rows={len(rows)} latest_items={len(latest_items)} snapshot={day}.min.json.gz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
