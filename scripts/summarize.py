"""Cost and latency of the recorded live run, from recordings/ (prints JSON)."""

import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent / "recordings"
agent = [json.loads(line)["value"] for line in (root / "agent.jsonl").read_text().splitlines() if line.strip()]
judge = [json.loads(line)["value"] for line in (root / "judge.jsonl").read_text().splitlines() if line.strip()]
meta = [a["_meta"] for a in agent]
latencies = sorted(m["latency_s"] for m in meta)
print(
    json.dumps(
        {
            "model": meta[0]["model"],
            "calls": len(meta),
            "mean_latency_s": sum(latencies) / len(latencies),
            "p90_latency_s": latencies[int(0.9 * (len(latencies) - 1))],
            "mean_cost_usd": sum(m["cost_usd"] for m in meta) / len(meta),
            "agent_cost_usd": sum(m["cost_usd"] for m in meta),
            "judge_calls": len(judge),
            "judge_cost_usd": sum(j["cost_usd"] for j in judge),
        },
        indent=2,
    )
)
