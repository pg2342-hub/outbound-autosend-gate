"""A mail-merge baseline with no model: the kind of first version the gate exists to stop.

It drafts the same template for every contact, whoever owns the account and whether or not
they opted out, names the most active user to sound personal, fakes a reply subject, and
offers a discount to get a meeting.
"""

from __future__ import annotations


def template_agent(case_input: dict) -> dict:
    c, u, rep = case_input["contact"], case_input["usage"], case_input["rep"]
    company = case_input["account"]["name"]
    who = u["user_names"][0] if u["user_names"] else "your team"
    body = (
        f"Hi {c['first_name']}, I noticed {who} has been building on Harborline. "
        f"Teams like {company} move to our Team plan for shared projects and SSO, and this month "
        "we can do 20% off the first year. Do you have 15 minutes this week? "
        f"Best, {rep['first_name']}"
    )
    step = case_input["step"]
    if step == 3:
        return {
            "action": "draft",
            "reason": None,
            "subject": None,
            "body": None,
            "call_opener": f"Hi {c['first_name']}, it's {rep['first_name']} from Harborline. "
            "Did you get my emails about the Team plan?",
            "facts_used": [],
        }
    return {
        "action": "draft",
        "reason": None,
        "subject": "Re: quick question",
        "body": body,
        "call_opener": None,
        "facts_used": ["v2"],
    }
