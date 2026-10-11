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
    compiler = SimpleNamespace(executed=True, status="test", compiler_versions=("0.8.20",), evidence=(), constraints=(), build_info_count=1, matched_source_count=1, source_ast_found=True)

    payload = _no_hypothesis_payload("fixture@pinned", compiler, result)
    surface = payload["surface_coverage"][0]

    assert surface["declared_modifiers"] == []
    assert surface["effective_modifiers"] == ["metaTx"]
    assert surface["modifier_provenance"] == "inherited_super_dispatch"
    assert payload["contracts"][0]["functions"][0]["declaring_source"] == str(source)
    assert payload["inherited_function_coverage"][0]["declaring_source"] == str(tmp_path / "Base.sol")
    assert payload["hypotheses"] == []
    assert payload["finding_gate"] == "NOT_READY"
