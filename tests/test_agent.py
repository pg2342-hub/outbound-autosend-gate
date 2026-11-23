"""The Claude agent's request shape, cost math and record/replay, with a fake client (no network)."""

import json
from types import SimpleNamespace

import pytest

from outbound.agent import ClaudeOutbound, system_prompt, user_message
from outbound.recorded import Tape, key, recording_agent, replay_agent

RECORD = {
    "action": "skip",
    "reason": "the contact opted out",
    "subject": None,
    "body": None,
    "call_opener": None,
    "facts_used": [],
}


class FakeMessages:
    def __init__(self, stop="end_turn"):
        self.calls, self.stop = [], stop

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            model=kw["model"],
            stop_reason=self.stop,
            content=[SimpleNamespace(type="text", text=json.dumps(RECORD))],
            usage=SimpleNamespace(
                input_tokens=2000, output_tokens=300, cache_creation_input_tokens=0, cache_read_input_tokens=0
            ),
        )


def fake_client(stop="end_turn"):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(stop)))


CALL = {"step": 1, "account": {"name": "Cobalt Ledger"}, "contact": {"first_name": "Nina", "opted_out": True}}


def test_request_uses_structured_output_and_fallbacks():
    client = fake_client()
    record = ClaudeOutbound(client=client)(CALL)
    sent = client.beta.messages.calls[0]
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["fallbacks"] == "default"
    assert "Harborline" in sent["system"] and "route_to_owner" in sent["system"]
    assert record["action"] == "skip"
    assert record["_meta"]["cost_usd"] == pytest.approx((2000 * 4 + 300 * 20) / 1e6)


def test_refusal_raises():
    with pytest.raises(RuntimeError):
        ClaudeOutbound(client=fake_client("refusal"))(CALL)


def test_prompt_contains_account():
    assert "Cobalt Ledger" in user_message(CALL) and '"opted_out": true' in user_message(CALL)
    assert "<policy>" in system_prompt() and "<seller_facts>" in system_prompt()


def test_record_then_replay_in_order(tmp_path):
    tape = Tape(tmp_path / "agent.jsonl")
    outputs = iter([{"n": 1}, {"n": 2}])
    rec = recording_agent(lambda _: next(outputs), tape)
    rec(CALL), rec(CALL)
    replay = replay_agent(Tape(tmp_path / "agent.jsonl"))
    assert [replay(CALL)["n"], replay(CALL)["n"]] == [1, 2]
    with pytest.raises(LookupError):
        replay(CALL)


def test_key_is_order_independent():
    assert key({"a": 1, "b": 2}) == key({"b": 2, "a": 1})
