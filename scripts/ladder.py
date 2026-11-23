"""Print the auto-send ladder for a golive results.json (markdown, or JSON with --json)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outbound.ladder import load, to_markdown

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--json"]
    results = args[0] if args else "reports/results.json"
    rows = load(results, Path(__file__).resolve().parent.parent / "evals" / "cases.yml")
    print(json.dumps(rows, indent=2) if "--json" in sys.argv else to_markdown(rows))
