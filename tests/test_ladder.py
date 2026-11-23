"""The auto-send ladder decides each step on its own record."""

from checks import checks
from golive_gate import Gate, evaluate, load_cases, run_eval
from golive_gate.report import write
from test_checks import CASES, correct

from outbound.ladder import decide, load, to_markdown

CRITICAL = {c.id for c in checks if c.critical}


def _results(fail_case=None, judged=True):
    cases = []
    for cid in CASES:
        failed = ["length"] if cid == fail_case else []
        cases.append({"id": cid, "runs": [{"run": 1, "failed_checks": failed, "error": ""}]})
    ids = [{"id": c.id, "critical": c.critical} for c in checks]
    if judged:
        ids.append({"id": "send_unedited", "critical": False})
    return {"cases": cases, "checks": ids}


RAW = [{"id": c.id, "input": c.input} for c in CASES.values()]


def test_clean_run_unlocks_every_step():
    rows = decide(_results(), RAW, CRITICAL)
    assert [r["decision"] for r in rows] == ["auto-send", "auto-send", "dialer without review"]


def test_one_miss_holds_only_its_own_step():
    rows = {r["step"]: r["decision"] for r in decide(_results("u02"), RAW, CRITICAL)}
    assert rows == {1: "auto-send", 2: "rep approval", 3: "dialer without review"}


def test_no_judge_means_no_auto_send():
    assert {r["decision"] for r in decide(_results(judged=False), RAW, CRITICAL)} == {"rep approval"}


def test_end_to_end_from_a_results_file(tmp_path):
    cases = load_cases("evals/cases.yml")
    result = run_eval(lambda inp: correct(next(c for c in cases if c.input == inp)), cases, checks, runs=1)
    gate = Gate.load("evals/gate.yml")
    write(tmp_path, result, gate, evaluate(gate, result))
    rows = load(tmp_path / "results.json", "evals/cases.yml")
    assert {r["decision"] for r in rows} == {"rep approval"}  # rules only, no judge verdicts yet
    assert "| 1. first email |" in to_markdown(rows)
