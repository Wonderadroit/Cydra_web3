from pathlib import Path

from cydra.hypothesis_seeds import generate_hypothesis_seeds
from cydra.models import ContractModel, FunctionModel


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


def test_classified_local_call_without_write_or_lifecycle_does_not_seed(tmp_path: Path):
    source = tmp_path / "Resolved.sol"
    source.write_text(
        "contract Resolved { "
        "function guardedHelper() internal onlyOwner { manager = manager; } "
        "function inspect() external { guardedHelper(); } "
        "address manager; modifier onlyOwner() { _; } }",
        encoding="utf-8",
    )
    helper = FunctionModel("guardedHelper", "internal", ("onlyOwner",), ("manager",), (), 1, source=str(source))
    inspect = FunctionModel("inspect", "external", (), (), (), 1, source=str(source))
    contract = ContractModel("Resolved", str(source), (helper, inspect), state_variables=("manager",))
    seeds = generate_hypothesis_seeds((contract,))
    assert all(seed.target_function != "inspect" for seed in seeds)
