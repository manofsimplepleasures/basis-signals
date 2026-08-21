#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="${BASIS_SIGNAL_DIR:-/opt/basis_signal}"
RAW_DIR="$BASE_DIR/raw"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$RAW_DIR" "$LOG_DIR" "$BASE_DIR/data/archive"
cd "$BASE_DIR"
python3 scripts/acceptance_intelligence.py \
  --pages "${BASIS_SIGNAL_PAGES:-4}" \
  --channels mrnadzor KIRILLPRIEMKA tehpriemka specnovostroy_ch revizor_priemka priemka_moscow pro_smarent iliilitop \
  --output-dir "$RAW_DIR" \
  >> "$LOG_DIR/update.log" 2>&1
python3 scripts/generate_site.py \
  --input "$RAW_DIR/acceptance-posts.jsonl" \
  --outdir "$BASE_DIR" \
  --days 14 \
  --limit 24 \
  --keep-days 60 \
  >> "$LOG_DIR/update.log" 2>&1
find "$LOG_DIR" -type f -name '*.log' -size +5M -exec sh -c 'tail -n 1000 "$1" > "$1.tmp" && mv "$1.tmp" "$1"' _ {} \;
