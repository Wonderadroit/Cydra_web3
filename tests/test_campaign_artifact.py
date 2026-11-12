from pathlib import Path
from types import SimpleNamespace

from cydra.models import ContractModel, FunctionModel
from scripts.run_authorization_campaign import _no_hypothesis_payload


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
    inherited_surface = payload["inherited_function_coverage"][0]
    assert inherited_surface["body_scope"] == "in_scope"
    assert inherited_surface["seed_decision"] == "not_evaluated:no_seed_trigger"
    assert inherited_surface["blocking_reason_code"] == "no_seed_trigger"


def test_campaign_artifact_records_blocked_seed_reason(tmp_path: Path):
    source = tmp_path / "Settler.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\\n"
        "contract Settler { function execute() public {} }\\n",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="execute", visibility="public", modifiers=(), writes=(),
        external_calls=(), line=2, source=str(source), body_scope="in_scope",
    )
    contract = ContractModel(
        name="Settler", source=str(source), functions=(),
        inherited_functions=(function,),
    )
    seed = SimpleNamespace(
        target_contract="Settler", target_function="execute", source_line=2,
        status="blocked",
        provenance=("unresolved_path:_execute:callee_effect_or_authorization_unclassified",),
    )
    result = SimpleNamespace(contracts=(contract,), invariants=(), evidence=(), seeds=(seed,))
    compiler = SimpleNamespace(
        executed=True, status="test", compiler_versions=("0.8.20",), evidence=(),
        constraints=(), build_info_count=1, matched_source_count=1,
        source_ast_found=True, source_dependency_count=1, unresolved_imports=(),
    )

    payload = _no_hypothesis_payload("fixture@pinned", compiler, result)
    inherited_surface = payload["inherited_function_coverage"][0]
    assert inherited_surface["body_scope"] == "in_scope"
    assert inherited_surface["seed_decision"] == "blocked:unresolved_callee_effects"
    assert inherited_surface["blocking_reason_code"] == "unresolved_callee_effects"
