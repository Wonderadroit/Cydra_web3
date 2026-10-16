from pathlib import Path
import shutil

import pytest

from cydra.authorization_pipeline import investigate_authorization
from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.foundry import ExecutionResult, run_foundry_test
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel
from cydra.reasoning import generate_access_control_hypotheses


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


def test_library_mutator_on_qualified_storage_variable_is_modeled(tmp_path: Path):
    source = tmp_path / "LibraryTarget.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "library SetLib { struct AddressSet { mapping(address => bool) values; } "
        "function add(AddressSet storage self, address item) internal { self.values[item] = true; } }\n"
        "contract LibraryTarget {\n"
        "  using SetLib for SetLib.AddressSet;\n"
        "  address public owner;\n"
        "  SetLib.AddressSet private _gateways;\n"
        "  modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }\n"
        "  function addGateway(address gateway) external { _gateways.add(gateway); }\n"
        "  function adminAddGateway(address gateway) external onlyOwner { _gateways.add(gateway); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = investigate_authorization(source, target="library-mutation-control@pinned")
    contract = next(item for item in result.contracts if item.name == "LibraryTarget")
    functions = {item.name: item for item in contract.functions}

    assert "_gateways" in contract.state_variables
    assert "_gateways" in functions["addGateway"].writes
    assert any(item.hypothesis_id == "H-AUTH-addGateway" for item in result.hypotheses)



def test_inherited_modifier_counts_only_when_override_calls_super(tmp_path: Path):
    source = tmp_path / "Derived.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Derived {\n"
        "  address public treasury;\n"
        "  function setTreasury(address next) external { super.setTreasury(next); }\n"
        "}\n",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="setTreasury", visibility="external", modifiers=(), writes=("treasury",),
        external_calls=(), line=4,
    )
    inherited = FunctionModel(
        name="setTreasury", visibility="public", modifiers=("onlyOwner",), writes=("treasury",),
        external_calls=(), line=12,
    )
    contract = ContractModel(
        name="Derived", source=str(source), functions=(function,),
        state_variables=("treasury",), inherited_functions=(inherited,),
    )

    # The base modifier executes because the override explicitly dispatches to super.
    assert generate_access_control_hypotheses(contract) == ()

    # Merely having a protected same-name base function must not mask an unguarded override.
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Derived {\n"
        "  address public treasury;\n"
        "  function setTreasury(address next) external { treasury = next; }\n"
        "}\n",
        encoding="utf-8",
    )
    hypotheses = generate_access_control_hypotheses(contract)
    assert {item.hypothesis_id for item in hypotheses} == {"H-AUTH-setTreasury"}


def test_lifecycle_write_emits_blocked_seed_even_without_supported_hypothesis(tmp_path: Path):
    from cydra.hypothesis_seeds import generate_hypothesis_seeds

    source = tmp_path / "Manager.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Manager {\n"
        "  address public manager;\n"
        "  function initializeManager(address next) external { manager = next; }\n"
        "}\n",
        encoding="utf-8",
    )

    result = investigate_authorization(source, target="manager-control@pinned")
    seeds = generate_hypothesis_seeds(result.contracts)

    assert any(
        seed.target_function == "initializeManager"
        and "manager" in seed.question
        and "manager" in seed.invariant
        and "changes" in seed.falsification
        and seed.status == "blocked"
        and "initialization_state" in seed.preconditions_needed
        for seed in seeds
    )
    # Seed generation is independent from the existing exploit-candidate filter.
    assert result.seeds
    assert any(seed.target_function == "initializeManager" for seed in result.seeds)


def test_seed_generator_keeps_protected_state_writer_as_question(tmp_path: Path):
    from cydra.hypothesis_seeds import generate_hypothesis_seeds

    source = tmp_path / "Protected.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Protected {\n"
        "  address public owner;\n"
        "  address public manager;\n"
        "  modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }\n"
        "  function setManager(address next) external onlyOwner { manager = next; }\n"
        "}\n",
        encoding="utf-8",
    )

    result = investigate_authorization(source)
    seeds = generate_hypothesis_seeds(result.contracts)
    assert any(seed.target_function == "setManager" for seed in seeds)
    assert all("vulnerable" not in seed.question.lower() for seed in seeds)



def test_guarded_setter_uses_authorized_vs_unauthorized_state_differential(tmp_path: Path):
    if shutil.which("forge") is None:
        pytest.skip("Foundry toolchain is not installed")
    project = tmp_path / "foundry-project"
    source = project / "src" / "OwnerTarget.sol"
    source.parent.mkdir(parents=True)
    (project / "test" / "generated").mkdir(parents=True)
    (project / "foundry.toml").write_text(
        "[profile.default]\\nsrc = 'src'\\ntest = 'test'\\n",
        encoding="utf-8",
    )
    source.write_text(
        "pragma solidity ^0.8.20;\\n"
        "contract OwnerTarget {\\n"
        "  address public owner;\\n"
        "  address public manager;\\n"
        "  constructor() { owner = msg.sender; }\\n"
        "  modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }\\n"
        "  function setManager(address next) external onlyOwner { manager = next; }\\n"
        "}\\n",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="setManager", visibility="external", modifiers=("onlyOwner",),
        writes=("manager",), external_calls=(), line=7,
        parameters=(ParameterModel(name="next", type="address"),), source=str(source),
    )
    model = ContractModel(
        name="OwnerTarget", source=str(source), functions=(function,), pragma="^0.8.20",
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
        discriminates=("authorized call changes manager", "unauthorized call reverts"),
        cost=1.0,
        planned_inputs=("address(0xCAFE)",),
        target_function="setManager",
    )
    generated = generate_blind_authorization_test_from_experiment(
        hypothesis, experiment, "../../src/OwnerTarget.sol", "OwnerTarget",
        project / "test" / "generated" / "OwnerTarget.t.sol", model,
    )
    harness = generated.read_text(encoding="utf-8")

    # Both controls execute the exact same calldata. The authorized control is
    # not inferred from the fallback "call must revert" assertion.
    assert "vm.prank(unauthorized);" in harness
    assert "vm.prank(authorized);" in harness
    assert "target.owner()" in harness
    assert "target.manager()" in harness
    assert "unauthorized differential control was not established" in harness
    assert "authorized control failed" in harness
    assert "authorized control did not change observed state" in harness
    assert "unauthorized caller successfully invoked protected administrative operation" not in harness

    execution = run_foundry_test(project, generated, experiment.experiment_id, "guarded-setter-fixture")
    assert execution.executed is True
    assert execution.tests_run == 1
    assert execution.status == "PASS"
    rejected = classify_authorization_blind_execution(hypothesis, execution)
    assert rejected.measurement_verdict == "rejected"
    assert rejected.benchmark_status == "not_confirmed"

    supported_execution = ExecutionResult(
        experiment_id=experiment.experiment_id, target="unguarded-setter-fixture",
        command=("forge", "test"), exit_code=1, executed=True, tests_run=1,
        tests_failed=1, status="FAIL",
        stdout="CYDRA_SECURITY_ASSERTION: unauthorized caller mutated modeled administrative state",
        stderr="",
    )
    supported = classify_authorization_blind_execution(hypothesis, supported_execution)
    assert supported.measurement_verdict == "supported"
    assert supported.benchmark_status == "confirmed"

    unmeasurable_execution = ExecutionResult(
        experiment_id=experiment.experiment_id, target="unmeasurable-fixture",
        command=("forge", "test"), exit_code=1, executed=True, tests_run=1,
        tests_failed=1, status="FAIL",
        stdout="CYDRA_MEASUREMENT_ASSERTION: authorized control failed", stderr="",
    )
    unmeasurable = classify_authorization_blind_execution(hypothesis, unmeasurable_execution)
    assert unmeasurable.measurement_verdict == "unmeasurable"
    assert unmeasurable.benchmark_status == "proposed"
