from pathlib import Path

from cydra.authorization_pipeline import investigate_authorization


def test_authorization_investigation_is_scoped_to_authorization(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Target {\n"
        "  address public owner;\n"
        "  address public operator;\n"
        "  modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }\n"
        "  function setTreasury(address next) external onlyOwner { operator = next; }\n"
        "  function setOperator(address next) external { operator = next; }\n"
        "}\n",
        encoding="utf-8",
    )

    result = investigate_authorization(source, target="fixture@pinned")

    assert result.target == "fixture@pinned"
    assert result.status in {"HYPOTHESES_READY", "NO_AUTH_HYPOTHESIS"}
    assert all(item.invariant_id == "INV-AUTH-001" for item in result.hypotheses)
    assert {item.hypothesis_id for item in result.hypotheses} <= {"H-AUTH-setOperator"}
    assert len(result.experiments) == len(result.hypotheses)


def test_no_hypothesis_is_not_reported_as_secure(tmp_path: Path):
    source = tmp_path / "ReadOnly.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract ReadOnly { function value() external pure returns (uint256) { return 1; } }",
        encoding="utf-8",
    )

    result = investigate_authorization(source)

    assert result.status == "NO_AUTH_HYPOTHESIS"
    assert result.hypotheses == ()
    assert result.experiments == ()


def test_payable_state_and_helper_mediated_writer_are_modeled(tmp_path: Path):
    source = tmp_path / "HelperTarget.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract HelperTarget {\n"
        "  address public owner;\n"
        "  address payable public treasury;\n"
        "  modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }\n"
        "  function _writeTreasury(address payable next) internal { treasury = next; }\n"
        "  function setTreasury(address payable next) external { _writeTreasury(next); }\n"
        "  function adminTreasury(address payable next) external onlyOwner { _writeTreasury(next); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = investigate_authorization(source, target="helper-mediated-control@pinned")

    contract = next(item for item in result.contracts if item.name == "HelperTarget")
    functions = {item.name: item for item in contract.functions}
    assert "treasury" in contract.state_variables
    assert "treasury" in functions["_writeTreasury"].writes
    assert "treasury" in functions["setTreasury"].writes
    assert any(
        effect.function == "setTreasury"
        and effect.state == "treasury"
        and effect.via_function == "_writeTreasury"
        for effect in result.derived_effects
    )
    assert any(item.hypothesis_id == "H-AUTH-setTreasury" for item in result.hypotheses)
