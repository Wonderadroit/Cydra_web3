from pathlib import Path

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis


def _generate(fixture: Path, contract_name: str, function_name: str, writes: tuple[str, ...], tmp_path: Path) -> str:
    source = fixture.read_text(encoding="utf-8")
    source_line = next(
        index for index, line in enumerate(source.splitlines(), start=1)
        if f"function {function_name}(" in line
    )
    model = ContractModel(
        name=contract_name,
        source=str(fixture.resolve()),
        pragma="^0.8.22",
        state_variables=writes,
        functions=(
            FunctionModel(
                name=function_name,
                visibility="external",
                modifiers=(),
                writes=writes,
                external_calls=(),
                line=source_line,
                parameters=(),
                source=str(fixture.resolve()),
            ),
        ),
    )
    hypothesis = Hypothesis(
        hypothesis_id=f"H-AUTH-{function_name}",
        claim=f"{function_name} may alter authority",
        invariant_id="INV-AUTH-001",
        target_function=function_name,
        attacker_capability="arbitrary external caller",
        expected_impact="authority membership can change",
        source_path=str(fixture.resolve()),
        declaring_contract=contract_name,
        source_line=source_line,
        display_label=f"H-AUTH-{function_name}",
    )
    experiment = Experiment(
        experiment_id=f"X-H-AUTH-{function_name}",
        hypothesis_id=hypothesis.hypothesis_id,
        action="Call as an unrelated actor and observe supported authority before and after.",
        discriminates=("authority membership changes", "no measurable authority change"),
        cost=1.0,
        target_function=function_name,
    )
    return generate_blind_authorization_test_from_experiment(
        hypothesis,
        experiment,
        f"../fixtures/{fixture.parent.name}/{fixture.name}",
        contract_name,
        tmp_path / f"Generated{contract_name}AuthTest.t.sol",
        model,
    ).read_text(encoding="utf-8")


def test_permissionless_factory_verdict_is_unmeasurable_until_authority_is_observable(tmp_path: Path):
    """Unknown authority is not rejected/safe; the verdict must remain unmeasurable."""
    fixture = Path(__file__).parent / "fixtures" / "permissionless_factory" / "PermissionlessFactory.sol"
    source = fixture.read_text(encoding="utf-8")
    assert "child = address(new PermissionlessChild())" in source
    assert "_isChild[child] = true" in source
    assert "function create() external" in source

    generated = _generate(fixture, "PermissionlessFactory", "create", ("_isChild",), tmp_path)
    assert "Verdict public verdict;" in generated
    assert "verdict = Verdict.Unmeasurable;" in generated
    assert 'verdict = Verdict.Unmeasurable; verdictReason = "no_authority_getter";' in generated
    assert "observedAuthorityModelGovernsState = false;" in generated
    assert "emit CydraVerdict" not in generated
    assert "require(false" not in generated
    assert "if (deployedAddress == address(0))" in generated
    assert "verdict = Verdict.Inconclusive;" in generated



def test_transfer_guard_factory_fresh_registry_key_is_not_supported(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "permissionless_factory" / "PermissionlessFactory.sol"
    source = fixture.read_text(encoding="utf-8")
    assert "contract TransferGuardFactory" in source
    assert "mapping(address => bool) private _isTransferGuard;" in source
    assert "address(new TransferGuard())" in source
    assert "_isTransferGuard[transferGuard] = true;" in source

    generated = _generate(
        fixture,
        "TransferGuardFactory",
        "createTransferGuard",
        ("_isTransferGuard",),
        tmp_path,
    )
    assert 'verdict = Verdict.Unmeasurable; verdictReason = "no_authority_getter";' in generated
    assert 'observedStateVariable = "_isTransferGuard";' in generated
    assert "observedStateVariableDeclared = true;" in generated
    assert "observedStateExistedBefore = false;" in generated
    assert "observedStateExistenceMeasured = true;" in generated
    assert "stateMeasurementAvailable = false;" in generated
    assert "observedAuthorityModelGovernsState = false;" in generated
    assert 'verdictReason = "unauthorized_preexisting_authority_governed_state_changed";' not in generated
