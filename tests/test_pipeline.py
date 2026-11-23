"""The live path end to end with fake Anthropic clients, then the same run replayed from the recording.

The oracle agent returns the expected record and the judge always passes, so both runs must reach GO
and the replay must make no API calls at all.
"""

import json
import sys
import types

import agent as agent_mod
import judge_checks
from golive_gate import Gate, evaluate, load_cases, run_eval
from test_checks import CASES, correct

from outbound import agent as A
from outbound.recorded import Tape


class FakeMessages:
    def __init__(self):
        self.by_user = {A.user_message(c.input): correct(c) for c in CASES.values()}
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        if "system" in kw:
            text = json.dumps(self.by_user[kw["messages"][0]["content"]])
        else:
            text = "VERDICT: PASS - meets the criterion"
        usage = types.SimpleNamespace(
            input_tokens=2500, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0
        )
        return types.SimpleNamespace(
            model=kw["model"],
            stop_reason="end_turn",
            content=[types.SimpleNamespace(type="text", text=text)],
            usage=usage,
        )


def test_live_then_replay(tmp_path, monkeypatch):
    fake = FakeMessages()
    client = types.SimpleNamespace(beta=types.SimpleNamespace(messages=fake))
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda **kw: client))
    monkeypatch.setenv("GOLIVE_LIVE", "1")
    monkeypatch.setattr(agent_mod, "AGENT_TAPE", Tape(tmp_path / "agent.jsonl"))
    monkeypatch.setattr(agent_mod, "_live", None)
    monkeypatch.setattr(judge_checks, "JUDGE_TAPE", Tape(tmp_path / "judge.jsonl"))
    monkeypatch.setattr(judge_checks, "_judge", None)

    cases = load_cases("evals/cases.yml")
    gate = Gate.load("evals/gate.yml")
    live = run_eval(agent_mod.live_agent, cases, judge_checks.checks, runs=2)
    assert evaluate(gate, live).decision == "go"
    live_calls = fake.calls
    assert live.total_cost_usd > 0 and live.total_judge_cost_usd > 0

    monkeypatch.delenv("GOLIVE_LIVE")
    monkeypatch.setattr(agent_mod, "AGENT_TAPE", Tape(tmp_path / "agent.jsonl"))
    monkeypatch.setattr(judge_checks, "JUDGE_TAPE", Tape(tmp_path / "judge.jsonl"))
    monkeypatch.setattr(judge_checks, "_judge", None)
    replay = run_eval(agent_mod.recorded_agent, cases, judge_checks.checks, runs=2)
    assert fake.calls == live_calls  # replay made no API calls
    assert evaluate(gate, replay).decision == "go"
    assert replay.total_judge_cost_usd == live.total_judge_cost_usd
