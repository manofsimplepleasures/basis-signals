#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="${BASIS_SIGNAL_DIR:-/opt/basis_signal}"
RAW_DIR="$BASE_DIR/raw"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$RAW_DIR" "$LOG_DIR" "$BASE_DIR/data/archive" "$BASE_DIR/data/snapshots"
cd "$BASE_DIR"
python3 scripts/acceptance_intelligence.py \
  --pages "${BASIS_SIGNAL_PAGES:-4}" \
  --channels mrnadzor KIRILLPRIEMKA tehpriemka specnovostroy_ch revizor_priemka priemka_moscow pro_smarent iliilitop cityprofmsk nikita_ooobrik expert_novostroy moydom_estate sudex priemka_komandask priemka_krd \
  --output-dir "$RAW_DIR" \
  2>&1 | tee -a "$LOG_DIR/update.log" "$RAW_DIR/collect.out"
FETCHED_TOTAL="$(python3 - <<'PY' "$RAW_DIR/collect.out"
import re, sys
text=open(sys.argv[1], encoding='utf-8', errors='ignore').read()
m=re.search(r'Fetched\s+(\d+)\s+posts', text)
print(m.group(1) if m else '')
PY
)"
python3 scripts/generate_site.py \
  --input "$RAW_DIR/acceptance-posts.jsonl" \
  --outdir "$BASE_DIR" \
  --days 14 \
  --limit 24 \
  --keep-days 60 \
  --fetched-total "${FETCHED_TOTAL:-0}" \
  >> "$LOG_DIR/update.log" 2>&1
python3 scripts/update_history.py \
  --latest "$BASE_DIR/data/latest.min.json" \
  --history "$BASE_DIR/data/signals.min.jsonl" \
  --snapshots "$BASE_DIR/data/snapshots" \
  >> "$LOG_DIR/update.log" 2>&1
find "$LOG_DIR" -type f -name '*.log' -size +5M -exec sh -c 'tail -n 1000 "$1" > "$1.tmp" && mv "$1.tmp" "$1"' _ {} \;
