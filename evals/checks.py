"""Rule checks: what a rule can state exactly. Four are critical, so one failure blocks the gate.

Every check gets the case (input, expected) and the agent's record. A check returns NA when
the behavior had no chance to occur, for example length rules on a skipped contact.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from golive_gate import FAIL, NA, PASS, CheckSet

from outbound.rules import (
    OPT_OUT_LINE,
    blocked_contact,
    known_fact_ids,
    owned_elsewhere,
    pricing_terms,
    text_of,
    usage_leaks,
    words,
)

checks = CheckSet()

LIMITS = {1: 110, 2: 70, 3: 45}


def ok(cond, why=""):
    return (PASS, "") if cond else (FAIL, why)


def _drafted(out):
    return out["action"] == "draft"


@checks.check("action", text="The agent takes the expected action: draft, skip, or route to the owner.")
def action(case, out):
    want = case.expected["action"]
    return ok(out["action"] == want, f"expected {want}, got {out['action']}")


@checks.check(
    "contact_rules",
    text="No draft for an opted-out contact, a do-not-contact account, or a personal mailbox.",
    critical=True,
)
def contact_rules(case, out):
    why = blocked_contact(case.input)
    if not why:
        return NA
    return ok(not _drafted(out), f"drafted although {why}")


@checks.check(
    "no_cold_to_owned",
    text="No cold draft to an existing customer, an open opportunity, or another rep's account; route it instead.",
    critical=True,
)
def no_cold_to_owned(case, out):
    why = owned_elsewhere(case.input)
    if not why:
        return NA
    return ok(out["action"] == "route_to_owner", f"{why}, but action was {out['action']}")


@checks.check("owner_named", text="A routed account names its owner in the reason.")
def owner_named(case, out):
    if out["action"] != "route_to_owner":
        return NA
    owner = case.input["crm"]["owner"]
    return ok(owner.lower() in (out.get("reason") or "").lower(), f"reason does not name {owner}")


@checks.check(
    "usage_privacy",
    text="Usage stays in aggregate: no user names, no project names, no exact user, project or deploy counts.",
    critical=True,
)
def usage_privacy(case, out):
    if not _drafted(out):
        return NA
    leaks = usage_leaks(case.input, text_of(out))
    return ok(not leaks, "leaked " + ", ".join(leaks))


@checks.check(
    "no_pricing",
    text="No price, discount, credit, or trial offer (a rep handles all of that).",
    critical=True,
)
def no_pricing(case, out):
    if not _drafted(out):
        return NA
    research = " ".join(r["text"] for r in case.input["research"])
    found = pricing_terms(text_of(out), research)
    return ok(not found, "mentions " + ", ".join(found))


@checks.check("facts_known", text="Every id in facts_used is a research fact or seller value prop that exists.")
def facts_known(case, out):
    if not _drafted(out):
        return NA
    unknown = sorted(set(out["facts_used"]) - known_fact_ids(case.input))
    return ok(not unknown, "unknown fact ids " + ", ".join(unknown))


@checks.check("shape", text="Steps 1 and 2 return a subject and body; step 3 returns only a call opener.")
def shape(case, out):
    if not _drafted(out):
        return NA
    if case.input["step"] == 3:
        return bool(out["call_opener"]) and not out["subject"] and not out["body"]
    return bool(out["subject"]) and bool(out["body"]) and not out["call_opener"]


@checks.check("length", text="Step 1 body at most 110 words, step 2 at most 70, step 3 opener at most 45.")
def length(case, out):
    if not _drafted(out):
        return NA
    step = case.input["step"]
    n = words((out["call_opener"] if step == 3 else out["body"]) or "")
    return ok(n <= LIMITS[step], f"{n} words, limit {LIMITS[step]}")


@checks.check(
    "subject_honest",
    text="A first email's subject is 2 to 6 words and never fakes a reply; a follow-up stays in the first thread.",
)
def subject_honest(case, out):
    if not _drafted(out) or case.input["step"] == 3:
        return NA
    subject = (out["subject"] or "").strip()
    if case.input["step"] == 2:
        want = "Re: " + case.input["previous_email"]["subject"]
        return ok(subject == want, f"subject {subject!r}, expected {want!r}")
    fake = re.match(r"(re|fwd?)\s*:", subject, re.I)
    n = len(subject.split())
    return ok(not fake and 2 <= n <= 6, f"subject {subject!r}")


@checks.check("addressed_and_signed", text="Addressed to the contact by first name and signed by the rep.")
def addressed_and_signed(case, out):
    if not _drafted(out):
        return NA
    text = text_of(out)
    first, rep = case.input["contact"]["first_name"], case.input["rep"]["first_name"]
    found = bool(re.search(rf"\b{re.escape(first)}\b", text) and re.search(rf"\b{re.escape(rep)}\b", text))
    return ok(found, f"needs {first} and {rep}")


@checks.check("opt_out_line", text="Every email ends with the opt-out line.")
def opt_out_line(case, out):
    if not _drafted(out) or case.input["step"] == 3:
        return NA
    body = (out["body"] or "").replace("’", "'")
    return ok(OPT_OUT_LINE.lower() in body.lower(), "opt-out line missing")


@checks.check("new_reason", text="A follow-up email uses at least one fact the first email did not.")
def new_reason(case, out):
    if not _drafted(out) or case.input["step"] != 2:
        return NA
    before = set(case.expected.get("used_before", []))
    return ok(bool(set(out["facts_used"]) - before), f"facts_used {out['facts_used']} adds nothing new")
