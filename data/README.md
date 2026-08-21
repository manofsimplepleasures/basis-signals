# Data

Public lightweight data committed to GitHub.

## Files

- `latest.min.json` - the latest public snapshot used by the page.
- `signals.min.jsonl` - cumulative deduplicated signal database. One JSON object per line.
- `snapshots/YYYY-MM-DD.min.json.gz` - compressed daily public snapshots.

## What is intentionally excluded

The server keeps fuller runtime files outside GitHub:

- `latest.json`
- `archive/YYYY-MM-DD.json.gz`
- raw parser outputs
- logs

The public dataset does not store raw Telegram HTML pages, media, or long unstructured dumps.
