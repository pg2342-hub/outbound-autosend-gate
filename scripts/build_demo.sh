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
python - <<'PY'
import html
import json
from pathlib import Path

s = json.loads(Path("docs/summary.json").read_text())
ladder = json.loads(Path("docs/ladder.json").read_text())
rows = "".join(
    f"<tr><td>{r['step']}. {html.escape(r['name'])}</td><td>{r['cases']}</td><td><b>{r['decision']}</b></td>"
    f"<td>{html.escape('; '.join(r['misses'][:4]) or 'every case passed every check on every run')}</td></tr>"
    for r in ladder
)
ladder_html = (
    "<h2>Auto-send ladder</h2><p>The gate below (13 rules plus the grounded judge) decides whether drafts may "
    "reach reps for approval. The ladder is "
    "stricter and works one sequence step at a time: a step may send without a rep only when every case at that "
    "step passed every check, including the judge's &ldquo;send unedited&rdquo;, on all 3 runs.</p>"
    "<table><tr><th>Step</th><th>Cases</th><th>Decision</th><th>Why</th></tr>" + rows + "</table>"
)
notes = {
    "docs/index.html": (
        "An AI outbound agent for a fictional cloud platform, graded on 30 constructed accounts (3 runs each) with "
        "<a href='https://github.com/pg2342-hub/golive-gate'>golive-gate</a>. Each account carries a product-usage "
        "signal, research facts and CRM state, including traps: opted-out contacts, existing customers, open deals, "
        "another rep's account, a personal mailbox, and a research note written as an instruction. "
        f"Recorded live run of {s['model']}: {s['calls']} agent calls, mean {s['mean_latency_s']:.1f} s and "
        f"${s['mean_cost_usd']:.4f} per account; judge ${s['judge_cost_usd']:.2f} in total. "
        "<a href='baseline/'>See a no-model mail-merge baseline blocked by the same gate</a>. "
        "<a href='https://github.com/pg2342-hub/outbound-autosend-gate'>Code on GitHub</a>."
        + ladder_html
    ),
    "docs/baseline/index.html": (
        "The no-model mail-merge baseline on the same 30 accounts and gate: it emails everyone, names the most "
        "active user, fakes a reply subject and offers a discount, so the gate blocks it. "
        "<a href='../'>Back to the Claude agent</a>."
    ),
}
for path, note in notes.items():
    p = Path(path)
    p.write_text(p.read_text().replace("</h1>", f"</h1>\n<p>{note}</p>", 1))
PY
touch docs/.nojekyll
echo "demo written to docs/ (recorded Claude run) and docs/baseline/ (mail-merge baseline)"
