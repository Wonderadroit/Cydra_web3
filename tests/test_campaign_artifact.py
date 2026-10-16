from pathlib import Path
from types import SimpleNamespace

import json
import pytest

from cydra.models import ContractModel, FunctionModel
from scripts.run_authorization_campaign import _no_hypothesis_payload, _persist_campaign_evidence


def test_campaign_artifact_preserves_inherited_modifier_provenance(tmp_path: Path):
    source = tmp_path / "Derived.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Derived {\n"
        "  function executeMetaTxn() public { super.executeMetaTxn(); }\n"
        "}\n",
        encoding="utf-8",
    )
    local = FunctionModel(
        name="executeMetaTxn", visibility="public", modifiers=(), writes=(),
        external_calls=(), line=3,
    )
    base = FunctionModel(
        name="executeMetaTxn", visibility="public", modifiers=("metaTx",), writes=(),
        external_calls=(), line=12, source=str(tmp_path / "Base.sol"),
    )
    contract = ContractModel(
        name="Derived", source=str(source), functions=(local,),
        inherits=("Base",), inherited_functions=(base,),
    )
    result = SimpleNamespace(contracts=(contract,), invariants=(), evidence=())
    compiler = SimpleNamespace(executed=True, status="test", compiler_versions=("0.8.20",), evidence=(), constraints=(), build_info_count=1, matched_source_count=1, source_ast_found=True, source_dependency_count=1, unresolved_imports=())

    payload = _no_hypothesis_payload("fixture@pinned", compiler, result)
    surface = payload["surface_coverage"][0]

    assert surface["declared_modifiers"] == []
    assert surface["effective_modifiers"] == ["metaTx"]
    assert surface["modifier_provenance"] == "inherited_super_dispatch"
    assert payload["contracts"][0]["functions"][0]["declaring_source"] == str(source)
    assert payload["inherited_function_coverage"][0]["declaring_source"] == str(tmp_path / "Base.sol")
    assert payload["hypotheses"] == []
    assert payload["finding_gate"] == "NOT_READY"


@pytest.mark.parametrize(
    ("exit_path", "payload"),
    [
        ("outcome_mismatch", {"classification": "NOT_CONFIRMED", "exit_reason": "expected_outcome_mismatch"}),
        ("constructor_rendering_failure", {"classification": "UNMEASURABLE", "failure_layer": "constructor_rendering"}),
        ("causal_verification_failure", {"classification": "NOT_CONFIRMED", "failure_layer": "causal_verification"}),
    ],
)
def test_campaign_evidence_persists_for_result_bearing_exit_paths(
    tmp_path: Path, exit_path: str, payload: dict
):
    generated = tmp_path / "test_generated.sol"
    generated.write_text("// exact generated test\\n", encoding="utf-8")
    output = tmp_path / "artifacts" / "authorization-campaign.json"

    _persist_campaign_evidence(output, payload, generated)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    preserved = output.parent / "generated-tests" / generated.name
    assert preserved.read_text(encoding="utf-8") == "// exact generated test\\n"


def test_campaign_evidence_persists_runner_aborted_before_result_construction(tmp_path: Path):
    generated = tmp_path / "test_generated.sol"
    generated.write_text("// exact generated test\\n", encoding="utf-8")
    output = tmp_path / "artifacts" / "authorization-campaign.json"

    _persist_campaign_evidence(output, None, generated, "fixture abort before payload")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["classification"] == "RUNNER_ABORTED"
    assert payload["finding_gate"] == "NOT_READY"
    assert payload["failure_reason"] == "fixture abort before payload"
    preserved = output.parent / "generated-tests" / generated.name
    assert preserved.read_text(encoding="utf-8") == "// exact generated test\\n"



def test_real_campaign_runner_persists_mismatch_json_and_generated_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Exercise main()'s real mismatch return and finally-based artifact persistence."""
    import subprocess
    import sys

    import scripts.run_authorization_campaign as campaign

    target = tmp_path / "target-repo"
    (target / "contracts").mkdir(parents=True)
    source = target / "contracts" / "Foo.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Foo { function setOwner(address) public {} }\n",
        encoding="utf-8",
    )
    subprocess.run(("git", "init", "--initial-branch=main", str(target)), check=True, capture_output=True)
    subprocess.run(("git", "-C", str(target), "config", "user.email", "cydra-test@example.invalid"), check=True)
    subprocess.run(("git", "-C", str(target), "config", "user.name", "CYDRA test"), check=True)
    subprocess.run(("git", "-C", str(target), "add", "."), check=True)
    subprocess.run(("git", "-C", str(target), "commit", "-m", "fixture target"), check=True, capture_output=True)
    target_ref = subprocess.run(
        ("git", "-C", str(target), "rev-parse", "HEAD"),
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    hypothesis = SimpleNamespace(
        invariant_id="INV-AUTH-001", hypothesis_id="H1", target_function="setOwner",
    )
    experiment = SimpleNamespace(hypothesis_id="H1", experiment_id="E1")
    function = SimpleNamespace(name="setOwner", visibility="public", modifiers=(), writes=())
    monkeypatch.setattr(
        campaign, "_materialize_target_dependencies",
        lambda project: {"status": "READY", "package_manager": "fixture", "lockfile": None, "confidence": "test"},
    )
    monkeypatch.setattr(
        campaign, "compile_state_effects",
        lambda project, source: SimpleNamespace(status="OK", evidence=()),
    )
    def investigate(target_source, **kwargs):
        contract = SimpleNamespace(name="Foo", source=str(target_source), functions=(function,))
        return SimpleNamespace(
            hypotheses=(hypothesis,), experiments=(experiment,), contracts=(contract,),
            seeds=(), invariants=(),
        )

    monkeypatch.setattr(campaign, "investigate_authorization", investigate)

    def prepare(checkout, target_source, execution_project):
        destination = execution_project / "src" / "Foo.sol"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(target_source.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(campaign, "_prepare_isolated_foundry_project", prepare)

    def generate(hyp, exp, import_path, contract_name, output, model):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("// generated authorization test fixture\n", encoding="utf-8")
        return output

    monkeypatch.setattr(campaign, "generate_blind_authorization_test_from_experiment", generate)
    monkeypatch.setattr(
        campaign, "run_foundry_test",
        lambda *args, **kwargs: SimpleNamespace(
            experiment_id="E1", target="fixture", command=("forge", "test"),
            exit_code=0, executed=True, tests_run=1, tests_failed=0,
            status="PASS", stdout="fixture execution", stderr="",
        ),
    )
    monkeypatch.setattr(
        campaign, "classify_authorization_blind_execution",
        lambda *args, **kwargs: SimpleNamespace(
            benchmark_status="not_confirmed",
            measurement_verdict="rejected",
            evidence=SimpleNamespace(evidence_id="fixture-evidence"),
        ),
    )

    output = tmp_path / "artifacts" / "authorization-campaign.json"
    monkeypatch.setattr(sys, "argv", [
        "run_authorization_campaign.py",
        "--target-repo", str(target),
        "--target-ref", target_ref,
        "--target-path", "contracts/Foo.sol",
        "--target-project", ".",
        "--expected-status", "confirmed",
        "--output", str(output),
    ])

    assert campaign.main() == 2

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["classification"] == "not_confirmed"
    assert payload["exit_reason"] == "expected_outcome_mismatch"
    preserved_tests = list((output.parent / "generated-tests").glob("*.sol"))
    assert len(preserved_tests) == 1
    assert preserved_tests[0].read_text(encoding="utf-8") == "// generated authorization test fixture\n"
