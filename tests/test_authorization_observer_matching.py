from pathlib import Path
import shutil

import pytest

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.foundry import run_foundry_test
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


@pytest.mark.parametrize(
    ("name", "guarded", "expected_verdict"),
    [
        ("UnprotectedTarget", False, "supported"),
        ("GuardedTarget", True, "rejected"),
    ],
)
def test_mapping_write_uses_one_hop_is_reader_for_authorization_differential(
    tmp_path: Path, name: str, guarded: bool, expected_verdict: str
):
    if shutil.which("forge") is None:
        pytest.skip("Foundry toolchain is not installed")

    project = tmp_path / name
    source = project / "src" / f"{name}.sol"
    test_dir = project / "test" / "generated"
    source.parent.mkdir(parents=True)
    test_dir.mkdir(parents=True)
    (project / "foundry.toml").write_text(
        "[profile.default]\nsrc = 'src'\ntest = 'test'\n",
        encoding="utf-8",
    )
    modifier = (
        "address public owner;\n"
        "  constructor() { owner = msg.sender; }\n"
        "  modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }\n"
        if guarded else ""
    )
    guard = " onlyOwner" if guarded else ""
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        f"contract {name} {{\n"
        "  mapping(uint256 => mapping(address => bool)) private _validatorsMap;\n"
        f"  {modifier}"
        "  function isValidator(uint256 virtualId, address validator) public view returns (bool) { "
        "return _validatorsMap[virtualId][account]; }\n"
        f"  function addValidator(uint256 virtualId, address validator) external{guard} {{ "
        "if (isValidator(virtualId, validator)) return; "
        "_validatorsMap[virtualId][validator] = true; }\n"
        "}\n",
        encoding="utf-8",
    )

    function = FunctionModel(
        name="addValidator",
        visibility="external",
        modifiers=("onlyOwner",) if guarded else (),
        writes=("_validatorsMap",),
        external_calls=(),
        line=6 if guarded else 4,
        parameters=(
            ParameterModel(name="virtualId", type="uint256"),
            ParameterModel(name="validator", type="address"),
        ),
        source=str(source),
    )
    model = ContractModel(
        name=name,
        source=str(source),
        functions=(function,),
        pragma="^0.8.20",
        state_variables=("_validatorsMap", "owner") if guarded else ("_validatorsMap",),
    )
    hypothesis = Hypothesis(
        hypothesis_id=f"H-AUTH-{name}",
        claim="An arbitrary caller must not add a validator.",
        invariant_id="INV-AUTH-001",
        target_function="addValidator",
        attacker_capability="arbitrary external caller",
        expected_impact="unauthorized validator registration",
    )
    experiment = Experiment(
        experiment_id=f"E-AUTH-{name}",
        hypothesis_id=hypothesis.hypothesis_id,
        action="call addValidator with a new validator",
        discriminates=("unauthorized caller mutates validator state", "unauthorized caller is rejected"),
        cost=1.0,
        planned_inputs=("1", "address(0x1001)"),
        target_function="addValidator",
    )
    generated = generate_blind_authorization_test_from_experiment(
        hypothesis,
        experiment,
        f"../../src/{name}.sol",
        name,
        test_dir / f"{name}.t.sol",
        model,
    )
    harness = generated.read_text(encoding="utf-8")
    assert "target.isValidator(1, nextValue)" in harness
    assert "target._validatorsMap" not in harness

    execution = run_foundry_test(project, generated, experiment.experiment_id, name)
    assert execution.executed is True
    assert execution.tests_run == 1
    outcome = classify_authorization_blind_execution(hypothesis, execution)
    assert outcome.measurement_verdict == expected_verdict


def test_preconditions_probe_checks_staticcall_observer_before_authority(tmp_path: Path):
    project = tmp_path / "PreconditionTarget"
    source = project / "src" / "PreconditionTarget.sol"
    test_dir = project / "test" / "generated"
    source.parent.mkdir(parents=True)
    test_dir.mkdir(parents=True)
    source.write_text(
        "pragma solidity ^0.8.20; contract PreconditionTarget { "
        "address public owner; constructor() { owner = msg.sender; } "
        "modifier onlyOwner() { require(msg.sender == owner); _; } "
        "mapping(uint256 => mapping(address => bool)) private _validatorsMap; "
        "function isValidator(uint256 virtualId, address account) public view returns (bool) { "
        "bool ignored = _validatorsMap[virtualId][validator]; ignored; "
        "revert(\"observer unavailable\"); } "
        "function addValidator(uint256, address) external onlyOwner { } }",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="addValidator", visibility="external", modifiers=("onlyOwner",),
        writes=("_validatorsMap",), external_calls=(), line=1,
        parameters=(ParameterModel("virtualId", "uint256"), ParameterModel("validator", "address")),
        source=str(source),
    )
    model = ContractModel(name="PreconditionTarget", source=str(source), functions=(function,), pragma="^0.8.20")
    hypothesis = Hypothesis("H-AUTH-precondition", "guarded setter", "INV-AUTH-001",
                            "addValidator", "arbitrary caller", "unauthorized mutation")
    experiment = Experiment("E-AUTH-precondition", hypothesis.hypothesis_id, "call setter",
                            ("mutation", "rejection"), 1.0,
                            planned_inputs=("1", "address(0x1001)"), target_function="addValidator")
    generated = generate_blind_authorization_test_from_experiment(
        hypothesis, experiment, "../../src/PreconditionTarget.sol", "PreconditionTarget",
        test_dir / "PreconditionTarget.t.sol", model,
    )
    harness = generated.read_text(encoding="utf-8")
    assert "address(target).staticcall(" in harness
    assert "preconditions_not_established:state_unreadable" in harness
    assert harness.index("preconditions_not_established:state_unreadable") < harness.index(
        "preconditions_not_established:authorized_control_unavailable"
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, "PreconditionTarget")
    assert execution.executed is True
    outcome = classify_authorization_blind_execution(hypothesis, execution)
    assert outcome.measurement_verdict == "unmeasurable"
    assert "preconditions_not_established:state_unreadable" in outcome.evidence.claim
