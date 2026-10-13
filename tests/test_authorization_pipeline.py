from pathlib import Path

from cydra.authorization_pipeline import investigate_authorization
from cydra.models import ContractModel, FunctionModel
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


def test_seeded_state_writer_promotes_without_authority_getter(tmp_path: Path):
    source = tmp_path / "PermissionlessFactory.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract PermissionlessFactory { "
        "mapping(address => bool) private _isChild; "
        "function create(address child) external { _isChild[child] = true; } "
        "}",
        encoding="utf-8",
    )

    result = investigate_authorization(source)

    assert any(seed.target_function == "create" and seed.status == "seed"
               and seed.observed_writes for seed in result.seeds)
    assert {item.target_function for item in result.hypotheses} == {"create"}
    assert len(result.experiments) == 1
    assert result.experiments[0].hypothesis_id == result.hypotheses[0].hypothesis_id


def test_modifier_restrictions_are_classified_structurally(tmp_path: Path):
    from cydra.reasoning import modifier_restriction_category

    source = tmp_path / "ModifierCategories.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\\n"
        "contract ModifierCategories {\\n"
        "  address public owner;\\n"
        "  address public slasher;\\n"
        "  bool private _entered;\\n"
        "  bool private _initializing;\\n"
        "  modifier nonReentrant() { require(!_entered, 'reentrant'); _entered = true; _; _entered = false; }\\n"
        "  modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }\\n"
        "  modifier onlyInitializing() { _checkInitializing(); _; }\\n"
        "  function _checkInitializing() internal view { require(_initializing, 'not initializing'); }\\n"
        "  function foo() external nonReentrant { slasher = msg.sender; }\\n"
        "  function bar() external onlyOwner { slasher = msg.sender; }\\n"
        "  function baz() external onlyOwner nonReentrant { slasher = msg.sender; }\\n"
        "  function qux() external onlyInitializing { slasher = msg.sender; }\\n"
        "}\\n",
        encoding="utf-8",
    )

    result = investigate_authorization(source, target="modifier-classification-fixture")
    contract = next(item for item in result.contracts if item.name == "ModifierCategories")
    functions = {item.name: item for item in contract.functions}

    assert modifier_restriction_category(contract, functions["foo"], "nonReentrant") == "other"
    assert modifier_restriction_category(contract, functions["bar"], "onlyOwner") == "authorization"
    assert modifier_restriction_category(contract, functions["baz"], "onlyOwner") == "authorization"
    assert modifier_restriction_category(contract, functions["qux"], "onlyInitializing") == "lifecycle"

    # Reentrancy protection is not mistaken for caller authorization.
    assert "foo" in {item.target_function for item in result.hypotheses}
    # A caller-identity guard suppresses the hypothesis even alongside nonReentrant.
    assert "bar" not in {item.target_function for item in result.hypotheses}
    assert "baz" not in {item.target_function for item in result.hypotheses}
    # Lifecycle-only surfaces remain honest blocked seeds, not authorization hypotheses.
    qux_seed = next(item for item in result.seeds if item.target_function == "qux")
    assert qux_seed.status == "blocked"
    assert "initialization_state" in qux_seed.preconditions_needed
    assert "qux" not in {item.target_function for item in result.hypotheses}
