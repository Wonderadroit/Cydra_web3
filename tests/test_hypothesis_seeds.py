from pathlib import Path

from cydra.hypothesis_seeds import generate_hypothesis_seeds
from cydra.models import ContractModel, FunctionModel
from cydra.solidity_model import parse_solidity
from cydra.reasoning import generate_access_control_hypotheses


def test_direct_write_emits_derived_seed(tmp_path: Path):
    source = tmp_path / "Direct.sol"
    source.write_text(
        "contract Direct { address manager; function setManager(address next) external { manager = next; } }",
        encoding="utf-8",
    )
    function = FunctionModel("setManager", "external", (), ("manager",), (), 1, source=str(source))
    contract = ContractModel("Direct", str(source), (function,), state_variables=("manager",))
    seed = generate_hypothesis_seeds((contract,))[0]
    assert seed.status == "seed"
    assert seed.invariant_source == "derived"
    assert any(item.startswith("observed_write:manager") for item in seed.provenance)


def test_unresolved_super_dispatch_emits_blocked_generic_seed(tmp_path: Path):
    source = tmp_path / "Derived.sol"
    source.write_text(
        "contract Derived { function executeMetaTxn() public { super.executeMetaTxn(); } }",
        encoding="utf-8",
    )
    function = FunctionModel("executeMetaTxn", "public", (), (), (), 1, source=str(source))
    contract = ContractModel("Derived", str(source), (function,))
    seeds = generate_hypothesis_seeds((contract,))
    assert len(seeds) == 1
    seed = seeds[0]
    assert seed.status == "blocked"
    assert seed.invariant_source == "generic"
    assert any("unresolved_path:super.executeMetaTxn" in item for item in seed.provenance)
    assert seed.analysis_budget == "direct-call-sites; one-inheritance-level; no-cross-contract-resolution"


def test_resolved_external_call_with_modeled_authorization_does_not_seed(tmp_path: Path):
    source = tmp_path / "Resolved.sol"
    source.write_text(
        "contract Resolved { "
        "function inspect(address registry) external view returns (bool) { return registry.isAllowed(msg.sender); } "
        "function isAllowed(address actor) external view returns (bool) { return actor != address(0); } }",
        encoding="utf-8",
    )
    inspect = FunctionModel(
        "inspect", "external", (), (), (("registry", "isAllowed"),), 1,
        authorization_predicates=("isAllowed(actor)",), source=str(source),
    )
    modeled_callee = FunctionModel(
        "isAllowed", "external", (), (), (), 1,
        authorization_predicates=("actor != address(0)",), source=str(source),
    )
    contract = ContractModel("Resolved", str(source), (inspect, modeled_callee))
    seeds = generate_hypothesis_seeds((contract,))
    assert all(seed.target_function != "inspect" for seed in seeds)



def test_inherited_body_out_of_scope_emits_blocked_seed(tmp_path: Path):
    source = tmp_path / "Derived.sol"
    source.write_text(
        "contract Derived { function executeMetaTxn() public { super.executeMetaTxn(); } }",
        encoding="utf-8",
    )
    function = FunctionModel("executeMetaTxn", "public", (), (), (), 1, source=str(source))
    inherited = FunctionModel(
        "executeMetaTxn", "public", ("onlySolver", "metaTx"), (), (), 10,
        source=str(tmp_path / "Base.sol"), body_scope="out_of_scope",
    )
    contract = ContractModel("Derived", str(source), (function,), inherited_functions=(inherited,))
    seeds = generate_hypothesis_seeds((contract,))
    assert len(seeds) == 1
    seed = seeds[0]
    assert seed.status == "blocked"
    assert seed.invariant_source == "generic"
    assert any("inherited_body_out_of_scope:" in item for item in seed.provenance)
    assert any("Base.sol::executeMetaTxn" in item for item in seed.provenance)


def test_seed_coverage_counts_as_measurement_not_finding_readiness():
    from scripts.run_authorization_campaign import _seed_coverage_allows_measurement

    assert _seed_coverage_allows_measurement([], [object()])
    assert not _seed_coverage_allows_measurement([object()], [object()])
    assert not _seed_coverage_allows_measurement([], [])



def test_inherited_scope_comes_only_from_compiler_closure(tmp_path: Path):
    child = tmp_path / "Child.sol"
    base = tmp_path / "Base.sol"
    base.write_text(
        "pragma solidity ^0.8.20; contract Base { address public router; "
        "function setRouter(address next) external { router = next; } }",
        encoding="utf-8",
    )
    child.write_text(
        "pragma solidity ^0.8.20; import './Base.sol'; contract Child is Base {}",
        encoding="utf-8",
    )

    # Base.sol exists for declaration parsing but is deliberately absent from
    # the compiler's exact source-unit closure: its body was not staged/analyzed.
    modeled = parse_solidity(child, compiler_closure=("Child.sol",))
    inherited = next(f for f in modeled[0].inherited_functions if f.name == "setRouter")
    assert inherited.declaring_contract == "Base"
    assert inherited.source == str(base.resolve())
    assert inherited.body_scope == "out_of_scope"


def test_read_only_balanceof_does_not_become_authorization_hypothesis(tmp_path: Path):
    source = tmp_path / "Token.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Token { "
        "function balanceOf(address) external view returns (uint256) { return 0; } }",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    assert not generate_access_control_hypotheses(contract)
