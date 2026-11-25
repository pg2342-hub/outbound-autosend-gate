#!/usr/bin/env bash
# Rebuild the GitHub Pages demo in docs/ from the recorded live run (no API key needed).
set -euo pipefail
cd "$(dirname "$0")/.."
golive run evals/golive.baseline.yml --out docs/baseline >/dev/null || true
rm -f docs/baseline/report.md
if [ ! -s recordings/agent.jsonl ]; then
  # no live run recorded yet: publish the baseline and say the live run is pending
  python scripts/pending_page.py > docs/index.html
  touch docs/.nojekyll
  echo "no recording yet: docs/index.html is a pending page, docs/baseline/ has the mail-merge baseline"
  exit 0
fi
golive run evals/golive.yml --out docs >/dev/null || true
python scripts/summarize.py > docs/summary.json
golive run evals/golive.ladder.yml --out reports/ladder >/dev/null || true
python scripts/ladder.py reports/ladder/results.json --json > docs/ladder.json
rm -f docs/report.md docs/baseline/report.md
python scripts/build_demo.py
echo "demo written to docs/ (recorded Claude run) and docs/baseline/ (mail-merge baseline)"
