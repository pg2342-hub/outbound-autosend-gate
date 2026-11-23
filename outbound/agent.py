"""The outbound agent: one Claude call per account, returning one record.

The model reads the seller facts and the outbound policy and writes the record as JSON
(structured output, so the shape is guaranteed). Rules in evals/checks.py then
grade it; the model is never asked to grade itself.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .schema import RECORD_SCHEMA

HERE = Path(__file__).parent
MODEL = "claude-opus-5-5"
EFFORT = "low"
# USD per million tokens (input, output), first-party list prices.
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}


def system_prompt() -> str:
    facts = (HERE / "seller.yml").read_text()
    policy = (HERE / "policy.md").read_text()
    return (
        "You are an outbound sales agent working for one sales rep. For each account you get, you decide whether "
        "to draft outreach, skip the contact, or route the account to its owner, and you end with one record.\n\n"
        f"<seller_facts>\n{facts}</seller_facts>\n\n<policy>\n{policy}</policy>\n\n"
        "Write the way a sharp, plain-spoken rep writes: short, specific, no hype."
    )


def user_message(case_input: dict) -> str:
    return (
        "<account_record>\n"
        + json.dumps(case_input, indent=2, sort_keys=True)
        + "\n</account_record>\n\nWrite the record for this account."
    )


class ClaudeOutbound:
    """Calls Claude through the Anthropic SDK. Reads the key from ANTHROPIC_API_KEY."""

    def __init__(self, model: str = MODEL, effort: str = EFFORT, client: Any = None) -> None:
        if client is None:
            import anthropic

            # retry rate limits and overloads for longer than the default 2 tries, so a 90-call run finishes
            client = anthropic.Anthropic(max_retries=6)
        self.client = client
        self.model = model
        self.effort = effort
        self._system = system_prompt()

    def __call__(self, case_input: dict) -> dict:
        start = time.perf_counter()
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": RECORD_SCHEMA}},
            system=self._system,
            messages=[{"role": "user", "content": user_message(case_input)}],
        )
        latency = time.perf_counter() - start
        cost = self.cost(response)
        if response.stop_reason == "refusal":
            raise RuntimeError("the model declined this account")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("the record was cut off at max_tokens")
        text = next(b.text for b in response.content if b.type == "text")
        record = json.loads(text)
        record["_meta"] = {
            "model": getattr(response, "model", self.model),
            "cost_usd": cost,
            "latency_s": round(latency, 3),
        }
        return record

    def cost(self, response: Any) -> float:
        price = PRICES.get(getattr(response, "model", self.model)) or PRICES.get(self.model, (0.0, 0.0))
        usage = response.usage
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        tokens_in = (usage.input_tokens or 0) + written * 1.25 + cached * 0.05
        return (tokens_in * price[0] + (usage.output_tokens or 0) * price[1]) / 1e6
