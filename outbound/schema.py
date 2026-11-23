"""The one record every case must end in."""

RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["draft", "skip", "route_to_owner"]},
        "reason": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Why it skipped or routed; null for a draft.",
        },
        "subject": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Steps 1 and 2 only."},
        "body": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Steps 1 and 2 only."},
        "call_opener": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Step 3 only."},
        "facts_used": {"type": "array", "items": {"type": "string"}, "description": "Ids of facts used."},
    },
    "required": ["action", "reason", "subject", "body", "call_opener", "facts_used"],
    "additionalProperties": False,
}
