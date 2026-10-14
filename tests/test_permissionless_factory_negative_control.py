from pathlib import Path

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis


def _generate(fixture: Path, contract_name: str, function_name: str, writes: tuple[str, ...], tmp_path: Path) -> str:
    source = fixture.read_text(encoding="utf-8")
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
                line=10,
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
        source_line=10,
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
