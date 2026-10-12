from __future__ import annotations

import json
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
output = log_path.read_text(encoding="utf-8", errors="replace")
pattern = r"CYDRA_VERDICT[:\s]+(supported|rejected|inconclusive|unmeasurable|[1-4])"
raw = re.findall(pattern, output, re.IGNORECASE)
labels = {"1": "supported", "2": "rejected", "3": "inconclusive", "4": "unmeasurable"}
named = [value.lower() for value in raw if value.lower() in {"supported", "rejected", "inconclusive", "unmeasurable"}]
numeric = [labels[value] for value in raw if value in labels]
expected = {"supported", "unmeasurable", "rejected", "inconclusive"}
fixture_counts = {name: named.count(name) for name in sorted(expected)}
generated_counts = {name: numeric.count(name) for name in sorted(expected)}
artifact = {
    "schema_version": 1,
    "source": "Runtime fixture assertions plus CYDRA-generated Foundry harness public verdict state",
    "verdicts": [
        {
            "verdict": name,
            "fixture_observations": fixture_counts[name],
            "generated_harness_observations": generated_counts[name],
        }
        for name in sorted(expected)
    ],
    "all_four_observed_once_per_path": (
        set(named) == expected
        and set(numeric) == expected
        and all(fixture_counts[name] == 1 and generated_counts[name] == 1 for name in expected)
    ),
}
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
print(json.dumps(artifact, indent=2))
if not artifact["all_four_observed_once_per_path"]:
    raise SystemExit("expected each of four verdicts once in fixtures and once in generated harnesses")
