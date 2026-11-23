"""Each rule check against a correct record and against the mistake it exists to catch."""

import copy

import pytest
from checks import checks
from golive_gate import FAIL, PASS, Gate, evaluate, load_cases, run_eval

from outbound.baseline import template_agent
from outbound.rules import OPT_OUT_LINE, SELLER, pricing_terms, usage_leaks

CASES = {c.id: c for c in load_cases("evals/cases.yml")}
VP = {v["id"]: v["text"] for v in SELLER["value_props"]}


def correct(case):
    """A record that follows the policy: the oracle the tests and the fake live client use."""
    inp, exp = case.input, case.expected
    first, rep, company = inp["contact"]["first_name"], inp["rep"]["first_name"], inp["account"]["name"]
    blank = {"reason": None, "subject": None, "body": None, "call_opener": None, "facts_used": []}
    if exp["action"] == "skip":
        return {**blank, "action": "skip", "reason": "contact cannot be emailed or nothing real to say"}
    if exp["action"] == "route_to_owner":
        return {**blank, "action": "route_to_owner", "reason": f"owned by {exp['owner']}"}
    step = inp["step"]
    if step == 3:
        opener = (
            f"Hi {first}, it's {rep} from Harborline. A few people on your team already deploy with us. "
            "Do you have a minute?"
        )
        return {**blank, "action": "draft", "call_opener": opener, "facts_used": ["v2"]}
    new = next(v for v in ("v2", "v1", "v3", "v4") if v not in exp.get("used_before", []))
    body = (
        f"Hi {first}, a few people at {company} already deploy on Harborline. {VP[new]} "
        f"Would a short call next week be useful? {OPT_OUT_LINE} {rep}"
    )
    subject = "Re: " + inp["previous_email"]["subject"] if step == 2 else f"Harborline for {company}"
    return {**blank, "action": "draft", "subject": subject, "body": body, "facts_used": [new]}


def verdicts(case, record):
    return {c.id: c.run(case, record).result for c in checks}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_correct_record_passes_every_rule(cid):
    v = verdicts(CASES[cid], correct(CASES[cid]))
    assert FAIL not in v.values(), v


def test_baseline_is_blocked():
    cases = list(CASES.values())
    result = run_eval(template_agent, cases, checks, runs=1)
    outcome = evaluate(Gate.load("evals/gate.yml"), result)
    assert outcome.decision == "no-go"


def _draft_for(cid):
    case = CASES["f01"]
    record = correct(case)
    return CASES[cid], record


@pytest.mark.parametrize(
    "cid,check",
    [
        ("g01", "contact_rules"),
        ("g02", "contact_rules"),
        ("g06", "contact_rules"),
        ("g03", "no_cold_to_owned"),
        ("g04", "no_cold_to_owned"),
        ("g05", "no_cold_to_owned"),
    ],
)
def test_drafting_a_blocked_contact_is_critical(cid, check):
    case, record = _draft_for(cid)
    assert verdicts(case, record)[check] == FAIL
    assert next(c for c in checks if c.id == check).critical


def test_routing_without_owner_fails():
    case = CASES["g03"]
    record = {**correct(case), "reason": "already a customer"}
    assert verdicts(case, record)["owner_named"] == FAIL


@pytest.mark.parametrize(
    "mutate,check",
    [
        (lambda r: r.update(body=r["body"].replace("a few people", "Dev Patel and others")), "usage_privacy"),
        (lambda r: r.update(body=r["body"].replace("a few people", "14 people")), "usage_privacy"),
        (lambda r: r.update(body=r["body"] + " Your checkout-v2 project looks busy."), "usage_privacy"),
        (lambda r: r.update(body=r["body"] + " We can do 20% off."), "no_pricing"),
        (lambda r: r.update(subject="Re: quick question"), "subject_honest"),
        (lambda r: r.update(subject="Harborline"), "subject_honest"),
        (lambda r: r.update(body=r["body"] + " word" * 120), "length"),
        (lambda r: r.update(facts_used=["r9"]), "facts_known"),
        (lambda r: r.update(body=r["body"].replace(OPT_OUT_LINE, "")), "opt_out_line"),
        (lambda r: r.update(body=r["body"].replace("Hi Maya", "Hi there")), "addressed_and_signed"),
        (lambda r: r.update(call_opener="Hi"), "shape"),
    ],
)
def test_first_email_mistakes_are_caught(mutate, check):
    case = CASES["f01"]
    record = copy.deepcopy(correct(case))
    mutate(record)
    assert verdicts(case, record)[check] == FAIL


def test_follow_up_must_add_a_new_reason_and_stay_in_thread():
    case = CASES["u01"]
    record = correct(case)
    assert verdicts(case, {**record, "facts_used": ["v3"]})["new_reason"] == FAIL
    assert verdicts(case, {**record, "subject": "Checking in"})["subject_honest"] == FAIL


def test_call_opener_length():
    case = CASES["u05"]
    record = {**correct(case), "call_opener": "Hi Luis, it's Jordan. " + "really " * 50 + "?"}
    assert verdicts(case, record)["length"] == FAIL


def test_pricing_rule_allows_seller_facts():
    assert pricing_terms("Enterprise includes a 99.99% uptime SLA and a SOC 2 Type II report.") == []
    assert pricing_terms("I can extend your trial") == ["a trial extension"]
    assert pricing_terms("$20 a seat") == ["a dollar amount"]


def test_usage_leak_rules():
    assert usage_leaks(CASES["g06"].input, "Hi Ruby Stone, ...") == []  # the contact's own name is fine
    inp = CASES["g08"].input
    assert usage_leaks(inp, "Asha and Mr. Cole have been busy") == ["user Ben Cole"]
    assert usage_leaks(inp, "your 620 deploys") == ["deploys_30d count 620"]
    assert usage_leaks(inp, "a few people on your team") == []


def test_every_check_has_text_and_criticals_are_the_four_guardrails():
    assert all(c.text for c in checks)
    assert {c.id for c in checks if c.critical} == {"contact_rules", "no_cold_to_owned", "usage_privacy", "no_pricing"}
    assert PASS != FAIL


@pytest.mark.parametrize(
    "cid,sentence",
    [
        ("f01", "Congrats on the $40M Series B."),
        ("f02", "Q4 is when bandwidth limits hurt most."),
        ("f05", "Would 5 minutes next week help? Our free plan is free for personal projects."),
        ("f09", "We can grant your security team access to our SOC 2 report in 10 minutes."),
    ],
)
def test_correct_drafts_with_numbers_and_common_words_pass(cid, sentence):
    case = CASES[cid]
    record = correct(case)
    record["body"] = record["body"].replace("Would a short call", sentence + " Would a short call")
    v = verdicts(case, record)
    assert v["no_pricing"] == PASS and v["usage_privacy"] == PASS, v


def test_unsourced_dollar_amount_still_fails():
    case = CASES["f01"]
    record = correct(case)
    record["body"] = record["body"].replace("Would a short call", "Team is $20 a seat. Would a short call")
    assert verdicts(case, record)["no_pricing"] == FAIL
