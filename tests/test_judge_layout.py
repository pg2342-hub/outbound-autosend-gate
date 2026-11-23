import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

import judge_checks


def test_judge_sees_subject_and_body_apart():
    text = judge_checks._draft({"action": "draft", "subject": "Build limits", "body": "Hi Maya,\n\nShort note."})
    assert text.startswith("Subject: Build limits\n\nHi Maya,")


def test_judge_sees_call_opener_as_spoken():
    text = judge_checks._draft({"action": "draft", "call_opener": "Hi Dana, it's Jordan."})
    assert text.startswith("Call opener (spoken by the rep):")


def test_send_unedited_judge_knows_the_policy():
    assert "<outbound_policy>" in judge_checks._unedited.text
    assert "won't follow up" in judge_checks._unedited.text


def test_pilot_gate_leaves_send_unedited_to_the_ladder():
    ids = [c.id for c in judge_checks.pilot_checks]
    assert "send_unedited" not in ids
    assert "grounded" in ids
    assert len(ids) == len(judge_checks.checks) - 1
