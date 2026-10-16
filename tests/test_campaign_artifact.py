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
