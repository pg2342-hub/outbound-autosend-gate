"""Plain helpers shared by the rule checks and the baseline."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

SELLER = yaml.safe_load((Path(__file__).parent / "seller.yml").read_text())
VALUE_PROP_IDS = {v["id"] for v in SELLER["value_props"]}
PERSONAL_DOMAINS = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me"}
OPT_OUT_LINE = "If this isn't relevant, just let me know and I won't follow up."

_PRICING = [
    (r"\$\s?\d", "a dollar amount"),
    (r"\b\d{1,3}\s?%\s*off\b", "a percent off"),
    (r"\bhalf off\b", "half off"),
    (r"\bdiscount", "a discount"),
    (r"\bcoupon", "a coupon"),
    (r"\bcredits?\b", "credits"),
    (r"\bfree (month|months|year|trial)s?\b|\bfree for (a|the|\d)", "a free period"),
    (r"\btrial extension|\bextend(ed)? (your|the) trial", "a trial extension"),
]


_USAGE_NOUNS = r"(people|users|members|engineers|developers|teammates|projects|apps|sites|deploys|deployments|builds)"


def text_of(out: dict) -> str:
    return " ".join(x for x in (out.get("subject"), out.get("body"), out.get("call_opener")) if x)


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’$%.-]+", text))


def blocked_contact(inp: dict) -> str:
    if inp["contact"]["opted_out"]:
        return "the contact opted out"
    if inp["crm"]["do_not_contact"]:
        return "the account is do-not-contact"
    if inp["contact"]["email"].split("@")[-1].lower() in PERSONAL_DOMAINS:
        return "the address is a personal mailbox"
    return ""


def owned_elsewhere(inp: dict) -> str:
    crm = inp["crm"]
    if crm["status"] == "customer":
        return "the account is a customer"
    if crm["status"] == "open_opportunity":
        return "the account has an open opportunity"
    if crm["owner"] != inp["rep"]["name"]:
        return f"the account is owned by {crm['owner']}"
    return ""


def usage_leaks(inp: dict, text: str) -> list[str]:
    u = inp["usage"]
    low = text.lower()
    leaks = []
    for name in u["user_names"]:
        contact = f"{inp['contact']['first_name']} {inp['contact']['last_name']}"
        if name == contact:
            continue  # the reader's own usage is not someone else's
        last = name.split()[-1]
        # full name anywhere, or the last name as a capitalized word (so "grant access" is not "Zoe Grant")
        if name.lower() in low or re.search(rf"\b{re.escape(last)}\b", text):
            leaks.append(f"user {name}")
    for project in u["project_names"]:
        if project.lower() in low:
            leaks.append(f"project {project}")
    for field in ("active_users", "projects", "deploys_30d"):
        n = u[field]
        if n and n > 1 and re.search(rf"(?<![\d.$]){n}\s+(\w+\s+)?{_USAGE_NOUNS}\b", low):
            leaks.append(f"{field} count {n}")
    return leaks


def pricing_terms(text: str, research: str = "") -> list[str]:
    """Pricing language in a draft. A dollar amount quoted from the research facts (a funding round) is allowed."""
    low = text.lower()
    found = []
    for pattern, label in _PRICING:
        hits = [m.group(0) for m in re.finditer(pattern, low)]
        if label == "a dollar amount":
            hits = [h for h in hits if not _in_research(h, low, research.lower())]
        if hits:
            found.append(label)
    return found


def _in_research(hit: str, low: str, research: str) -> bool:
    for m in re.finditer(r"\$\s?\d[\d,.]*\s?(m|b|k|million|billion)?", low):
        if m.group(0).startswith(hit) and m.group(0).strip() in research:
            return True
    return False


def known_fact_ids(inp: dict) -> set[str]:
    return {r["id"] for r in inp["research"]} | VALUE_PROP_IDS
