from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from cydra.authorization_pipeline import investigate_authorization
from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.foundry import run_foundry_test
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


VIRTUALS_REPO = "https://github.com/code-423n4/2025-04-virtuals-protocol.git"
VIRTUALS_REF = "28e93273daec5a9c73c438e216dde04c084be452"
VIRTUALS_SOURCE = "contracts/virtualPersona/AgentNftV2.sol"


def _fixture_case(root: Path, *, guarded: bool) -> dict[str, str]:
    case = "guarded-setter-fixture" if guarded else "unguarded-setter-fixture"
    expected = "rejected" if guarded else "supported"
    project = root / case
    source = project / "src" / "CorpusTarget.sol"
    source.parent.mkdir(parents=True)
    (project / "test" / "generated").mkdir(parents=True)
    (project / "foundry.toml").write_text(
        "[profile.default]\nsrc = 'src'\ntest = 'test'\n",
        encoding="utf-8",
    )
    modifier = 'modifier onlyOwner() { require(msg.sender == owner, "owner"); _; }\n' if guarded else ""
    guard = " onlyOwner" if guarded else ""
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract CorpusTarget {\n"
        "  address public owner;\n"
        "  address public manager;\n"
        "  constructor() { owner = msg.sender; }\n"
        f"  {modifier}"
        f"  function setManager(address next) external{guard} {{ manager = next; }}\n"
        "}\n",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="setManager",
        visibility="external",
        modifiers=("onlyOwner",) if guarded else (),
        writes=("manager",),
        external_calls=(),
        line=7,
        parameters=(ParameterModel(name="next", type="address"),),
        source=str(source),
    )
    model = ContractModel(
        name="CorpusTarget",
        source=str(source),
        functions=(function,),
        pragma="^0.8.20",
        state_variables=("owner", "manager"),
    )
    hypothesis = Hypothesis(
        hypothesis_id="H-AUTH-setManager",
        claim="An arbitrary caller must not change manager.",
        invariant_id="INV-AUTH-001",
        target_function="setManager",
        attacker_capability="arbitrary external caller",
        expected_impact="unauthorized manager mutation",
    )
    experiment = Experiment(
        experiment_id="E-AUTH-setManager",
        hypothesis_id=hypothesis.hypothesis_id,
        action="call setManager with a state-changing address",
        discriminates=("unauthorized caller cannot mutate manager",),
        cost=1.0,
        planned_inputs=("address(0xCAFE)",),
        target_function="setManager",
    )
    generated = generate_blind_authorization_test_from_experiment(
        hypothesis,
        experiment,
        "../../src/CorpusTarget.sol",
        "CorpusTarget",
        project / "test" / "generated" / "CorpusTarget.t.sol",
        model,
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, case)
    outcome = classify_authorization_blind_execution(hypothesis, execution)
    actual = outcome.measurement_verdict
    layer = "none" if actual == expected else (
        "experiment_execution" if actual == "unmeasurable" else "verdict"
    )
    print(
        f"CORPUS_CASE case={case} expected={expected} actual={actual} "
        f"failure_layer={layer} execution_status={execution.status} "
        f"tests_run={execution.tests_run} exit={execution.exit_code}"
    )
    return {
        "case": case,
        "expected_outcome": expected,
        "actual_outcome": actual,
        "failure_layer": layer,
    }


def _virtuals_case(root: Path) -> dict[str, str]:
    case = f"virtuals-addValidator@{VIRTUALS_REF[:12]}"
    expected = "unmeasurable"
    output = root / "virtuals" / "authorization-campaign.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve().with_name("run_authorization_campaign.py")),
        "--target-repo", VIRTUALS_REPO,
        "--target-ref", VIRTUALS_REF,
        "--target-path", VIRTUALS_SOURCE,
        "--target-project", ".",
        "--expected-status", "confirmed",
        "--output", str(output),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            timeout=2700,
            check=False,
        )
    except subprocess.TimeoutExpired:
        row = {
            "case": case,
            "expected_outcome": expected,
            "actual_outcome": "unmeasurable",
            "failure_layer": "target_execution_timeout",
        }
        print(f"CORPUS_CASE case={case} expected={expected} actual=unmeasurable failure_layer=target_execution_timeout")
        return row

    payload = {}
    if output.is_file():
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    actual = payload.get("measurement_verdict")
    execution = payload.get("blind_execution") or {}
    if actual not in {"supported", "rejected", "unmeasurable"}:
        classification = payload.get("classification")
        if classification == "confirmed":
            actual = "supported"
        elif classification == "not_confirmed":
            # Legacy one-sided output is not accepted as a differential verdict.
            actual = "unmeasurable"
        else:
            actual = "unmeasurable"

    stderr = str(execution.get("stderr", ""))
    failure_reason = str(payload.get("failure_reason", "")) + " " + stderr
    if actual == "unmeasurable":
        if "no matching public scalar getter" in failure_reason or "observed state getter" in failure_reason:
            layer = "state_observation"
        elif payload.get("classification") == "NO_AUTH_HYPOTHESIS":
            layer = "hypothesis_conversion"
        elif "clone" in failure_reason.lower() or "fetch" in failure_reason.lower():
            layer = "target_intake"
        elif execution.get("status") == "UNMEASURABLE":
            layer = "experiment_preconditions"
        elif not payload:
            layer = "target_intake" if completed.returncode else "artifact_persistence"
        else:
            layer = "hypothesis_conversion"
    else:
        layer = "none" if actual == expected else "experiment"
    print(
        f"CORPUS_CASE case={case} expected={expected} actual={actual} "
        f"failure_layer={layer} returncode={completed.returncode}"
    )
    if completed.stdout:
        print(completed.stdout[-6000:])
    if completed.stderr:
        print(completed.stderr[-6000:])
    return {
        "case": case,
        "expected_outcome": expected,
        "actual_outcome": actual,
        "failure_layer": layer,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen three-case authorization measurement corpus.")
    parser.add_argument(
        "--score-output",
        type=Path,
        default=Path("benchmarks/authorization-corpus-score.json"),
    )
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="cydra-authorization-corpus-"))
    try:
        rows = [
            _fixture_case(root, guarded=True),
            _fixture_case(root, guarded=False),
            _virtuals_case(root),
        ]
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    args.score_output.parent.mkdir(parents=True, exist_ok=True)
    args.score_output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    matched = sum(row["expected_outcome"] == row["actual_outcome"] for row in rows)
    print(f"CORPUS_SCORE matched={matched}/{len(rows)}")
    print(args.score_output.read_text(encoding="utf-8"))
    return 0 if matched == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
