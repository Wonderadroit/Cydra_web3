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

expected_harnesses = {
    "GeneratedBrokenSetupRuntimeVerdictTest.t.sol": "inconclusive",
    "GeneratedGuardedAuthorityRuntimeVerdictTest.t.sol": "rejected",
    "GeneratedPermissionlessFactoryRuntimeVerdictTest.t.sol": "unmeasurable",
    "GeneratedVulnerableAuthorityRuntimeVerdictTest.t.sol": "supported",
}
generated_harnesses = {}
section_pattern = re.compile(
    r"Ran 1 test for test/generated/(Generated[^:]+):CydraBlindAuthorizationTest"
    r"([\s\S]*?)(?=\nRan \d+ tests? for test/generated/|\nRan \d+ test suite|\Z)"
)
for match in section_pattern.finditer(output):
    filename, section = match.group(1), match.group(2)
    verdict_match = re.search(pattern, section, re.IGNORECASE)
    raw_verdict = verdict_match.group(1).lower() if verdict_match else None
    observed_verdict = labels.get(raw_verdict, raw_verdict) if raw_verdict else None
    expected_verdict = expected_harnesses.get(filename)
    generated_harnesses[filename] = {
        "expected_verdict": expected_verdict,
        "observed_verdict": observed_verdict,
        "matches": observed_verdict == expected_verdict and expected_verdict is not None,
    }

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
    "generated_harnesses": generated_harnesses,
    "all_four_observed_once_per_path": (
        set(named) == expected
        and set(numeric) == expected
        and all(fixture_counts[name] == 1 and generated_counts[name] == 1 for name in expected)
    ),
    "each_generated_harness_matches_expected_verdict": (
        set(generated_harnesses) == set(expected_harnesses)
        and all(item["matches"] for item in generated_harnesses.values())
    ),
}
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
print(json.dumps(artifact, indent=2))
if not artifact["all_four_observed_once_per_path"] or not artifact["each_generated_harness_matches_expected_verdict"]:
    raise SystemExit("runtime verdicts did not match the four fixture-specific expectations")
