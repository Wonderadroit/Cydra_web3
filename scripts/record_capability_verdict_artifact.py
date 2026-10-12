from __future__ import annotations

import json
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
output = log_path.read_text(encoding="utf-8", errors="replace")
observed = re.findall(r"CYDRA_VERDICT\s+([a-z]+)", output)
expected = {"supported", "unmeasurable", "rejected", "inconclusive"}
counts = {name: observed.count(name) for name in sorted(expected)}
artifact = {
    "schema_version": 1,
    "source": "CYDRA-generated Foundry harness public verdict state",
    "verdicts": [{"verdict": name, "observations": counts[name]} for name in sorted(expected)],
    "all_four_observed_once": set(observed) == expected and all(counts[name] == 1 for name in expected),
}
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
print(json.dumps(artifact, indent=2))
if not artifact["all_four_observed_once"]:
    raise SystemExit("expected each runtime verdict exactly once")
