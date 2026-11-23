"""The auto-send ladder: which sequence steps may send without a rep, decided per step.

The pilot gate (evals/gate.yml) decides whether drafts may reach reps at all. The ladder is
stricter and works one step at a time: a step earns auto-send (for call openers, which a rep
speaks, loading into the dialer without review) only when every case at that
step passed every check, including the judge's "send unedited", on every run, with no critical
failure anywhere at that step. Otherwise the step stays on rep approval. In production the same
rule runs on real rep decisions (drafts sent unedited) instead of the judge, and once a step is on
auto-send, the critical checks still run before every send and reps review a random 1 in 10 after.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

JUDGE_CHECK = "send_unedited"
STEP_NAMES = {1: "first email", 2: "follow-up email", 3: "call opener"}
# a rep speaks the call opener, so its top rung is loading into the dialer without review, not sending
TOP_RUNG = {3: "dialer without review"}


def decide(results: dict, cases: list[dict], critical: set[str]) -> list[dict]:
    judged = any(c["id"] == JUDGE_CHECK for c in results["checks"])
    step_of = {c["id"]: c["input"]["step"] for c in cases}
    rows = []
    for step in sorted(set(step_of.values())):
        ids = [cid for cid, s in step_of.items() if s == step]
        misses, crit = [], []
        for case in results["cases"]:
            if case["id"] not in ids:
                continue
            for run in case["runs"]:
                failed = run["failed_checks"] + (["error"] if run["error"] else [])
                if failed:
                    misses.append(f"{case['id']} run {run['run']}: {', '.join(failed)}")
                crit += [f"{case['id']} {c}" for c in run["failed_checks"] if c in critical]
        if not judged:
            misses.append(f"no {JUDGE_CHECK} verdicts in this run")
        held = not misses
        rows.append(
            {
                "step": step,
                "name": STEP_NAMES.get(step, f"step {step}"),
                "cases": len(ids),
                "decision": TOP_RUNG.get(step, "auto-send") if held else "rep approval",
                "critical": sorted(set(crit)),
                "misses": misses,
            }
        )
    return rows


def load(results_path: str | Path, cases_path: str | Path) -> list[dict]:
    results = json.loads(Path(results_path).read_text())
    cases = yaml.safe_load(Path(cases_path).read_text())["cases"]
    critical = {c["id"] for c in results["checks"] if c["critical"]}
    return decide(results, cases, critical)


def to_markdown(rows: list[dict]) -> str:
    out = ["| Step | Cases | Decision | Why |", "|---|---|---|---|"]
    for r in rows:
        why = "every case passed every check on every run" if not r["misses"] else f"{len(r['misses'])} miss(es)"
        if r["critical"]:
            more = len(r["critical"]) - 3
            shown = ", ".join(r["critical"][:3]) + (f" and {more} more" if more > 0 else "")
            why += f"; critical: {shown}"
        out.append(f"| {r['step']}. {r['name']} | {r['cases']} | **{r['decision']}** | {why} |")
    return "\n".join(out)
