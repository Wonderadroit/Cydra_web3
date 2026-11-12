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


def test_inherited_effect_path_is_evaluated_once(tmp_path: Path):
    source = tmp_path / "Base.sol"
    source.write_text(
        'contract Base { function execute() public { target.call(""); } }',
        encoding="utf-8",
    )
    inherited = FunctionModel(
        "execute", "public", (), (), (), 1, source=str(source),
        body_scope="in_scope",
    )
    contract = ContractModel("Child", str(source), (), inherited_functions=(inherited,))
    seeds = generate_hypothesis_seeds((contract,))
    assert len(seeds) == 1
    assert seeds[0].target_function == "execute"
    assert seeds[0].status == "blocked"


def test_direct_declaration_wins_over_same_inherited_signature(tmp_path: Path):
    source = tmp_path / "Child.sol"
    source.write_text(
        "contract Child { function setValue(uint256 next) external { value = next; } }",
        encoding="utf-8",
    )
    direct = FunctionModel(
        "setValue", "external", (), ("value",), (), 1,
        parameters=(), source=str(source),
    )
    inherited = FunctionModel(
        "setValue", "external", (), (), (), 10,
        parameters=(), source=str(tmp_path / "Base.sol"),
    )
    contract = ContractModel(
        "Child", str(source), (direct,), state_variables=("value",),
        inherited_functions=(inherited,),
    )
    seeds = generate_hypothesis_seeds((contract,))
    assert len(seeds) == 1
    assert seeds[0].source == str(source)


def test_nearest_inherited_declaration_wins_over_distant_ancestor(tmp_path: Path):
    nearest_source = tmp_path / "Parent.sol"
    distant_source = tmp_path / "Grandparent.sol"
    nearest_source.write_text(
        "contract Parent { function setValue(uint256 next) external { value = next; } }",
        encoding="utf-8",
    )
    distant_source.write_text(
        "contract Grandparent { function setValue(uint256 next) external {} }",
        encoding="utf-8",
    )
    nearest = FunctionModel(
        "setValue", "external", (), ("value",), (), 5,
        parameters=(), source=str(nearest_source),
    )
    distant = FunctionModel(
        "setValue", "external", (), (), (), 8,
        parameters=(), source=str(distant_source),
    )
    contract = ContractModel(
        "Child", str(nearest_source), (), state_variables=("value",),
        inherited_functions=(nearest, distant),
    )
    seeds = generate_hypothesis_seeds((contract,))
    assert len(seeds) == 1
    assert seeds[0].source == str(nearest_source)
    assert seeds[0].status == "seed"


def test_inherited_functions_dedupe_by_signature_not_line_and_keep_overloads(tmp_path: Path):
    from cydra.solidity_model import parse_solidity

    grandparent = tmp_path / "Grandparent.sol"
    parent = tmp_path / "Parent.sol"
    child = tmp_path / "Child.sol"
    grandparent.write_text(
        "pragma solidity ^0.8.20; contract Grandparent { "
        "function touch(uint256 value) internal {} "
        "function touch(address value) internal {} }",
        encoding="utf-8",
    )
    parent.write_text(
        'pragma solidity ^0.8.20; import "./Grandparent.sol"; '
        "contract Parent is Grandparent { function touch(uint256 value) internal {} }",
        encoding="utf-8",
    )
    child.write_text(
        'pragma solidity ^0.8.20; import "./Parent.sol"; contract Child is Parent {}',
        encoding="utf-8",
    )

    contract = next(item for item in parse_solidity(child) if item.name == "Child")
    touches = [item for item in contract.inherited_functions if item.name == "touch"]
    signatures = [
        (item.name, tuple(parameter.type.strip() for parameter in item.parameters))
        for item in touches
    ]
    assert signatures.count(("touch", ("uint256",))) == 1
    assert signatures.count(("touch", ("address",))) == 1
    uint_touch = next(item for item in touches if item.parameters[0].type.strip() == "uint256")
    assert uint_touch.source == str(parent.resolve())



def test_bounded_walk_resolves_internal_effects_with_provenance_and_depth(tmp_path: Path):
    from cydra.hypothesis_seeds import _bounded_callee_walk

    source = tmp_path / "SettlerLike.sol"
    source.write_text(
        "contract SettlerLike { uint256 balance; "
        "function execute() external { _execute(); } "
        "function _execute() internal { _write(); } "
        "function _write() internal { balance = 1; } }",
        encoding="utf-8",
    )
    execute = FunctionModel("execute", "external", (), (), (), 1, source=str(source))
    run = FunctionModel("_execute", "internal", (), (), (), 1, source=str(source))
    write = FunctionModel("_write", "internal", (), ("balance",), (), 1, source=str(source))
    contract = ContractModel(
        "SettlerLike", str(source), (execute, run, write), state_variables=("balance",)
    )

    effects, provenance, blocker, depth = _bounded_callee_walk(contract, execute)
    assert blocker is None
    assert "resolved_effects" in effects
    assert "write:balance" in effects
    assert any("effect_provenance:write:balance:" in item for item in provenance)
    assert depth == 2


def test_bounded_walk_stops_at_signature_authorization_boundary(tmp_path: Path):
    from cydra.hypothesis_seeds import _bounded_callee_walk

    source = tmp_path / "SignatureBoundary.sol"
    source.write_text(
        "contract SignatureBoundary { "
        "function executeWithPermit() external { _dispatchPermit(); } "
        "function _dispatchPermit() internal {} }",
        encoding="utf-8",
    )
    entry = FunctionModel("executeWithPermit", "external", (), (), (), 1, source=str(source))
    dispatch = FunctionModel("_dispatchPermit", "internal", (), (), (), 1, source=str(source))
    contract = ContractModel("SignatureBoundary", str(source), (entry, dispatch))

    effects, provenance, blocker, _depth = _bounded_callee_walk(contract, entry)
    assert blocker == "blocked:signature_authorization_unsupported"
    assert any("blocked:signature_authorization_unsupported" in item for item in provenance)


def test_bounded_walk_fails_closed_on_delegatecall_storage_context(tmp_path: Path):
    from cydra.hypothesis_seeds import _bounded_callee_walk

    source = tmp_path / "Delegate.sol"
    source.write_text(
        'contract Delegate { function execute(address target, bytes memory data) external { target.delegatecall(data); } }',
        encoding="utf-8",
    )
    entry = FunctionModel("execute", "external", (), (), (), 1, source=str(source))
    contract = ContractModel("Delegate", str(source), (entry,))

    _effects, _provenance, blocker, _depth = _bounded_callee_walk(contract, entry)
    assert blocker == "blocked:delegatecall_storage_context_unmodeled"
