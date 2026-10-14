from pathlib import Path

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


FIXTURE = Path(__file__).parent / "fixtures" / "state_control" / "StateControlFixture.sol"


def _generate(contract_name: str, *, guarded: bool, tmp_path: Path) -> str:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    signature = (
        "    function setRouter(address nextRouter) external onlyOwner {"
        if guarded
        else "    function setRouter(address nextRouter) external {"
    )
    source_line = lines.index(signature) + 1
    function = FunctionModel(
        name="setRouter",
        visibility="external",
        modifiers=("onlyOwner",) if guarded else (),
        writes=("router",),
        external_calls=(),
        line=source_line,
        parameters=(ParameterModel(name="nextRouter", type="address"),),
        source=str(FIXTURE.resolve()),
    )
    model = ContractModel(
        name=contract_name,
        source=str(FIXTURE.resolve()),
        pragma="^0.8.22",
        state_variables=("router",),
        functions=(function,),
    )
    hypothesis = Hypothesis(
        hypothesis_id=f"H-AUTH-{contract_name}-setRouter",
        claim="An unauthorized caller may change a pre-existing privileged configuration slot.",
        invariant_id="INV-AUTH-001",
        target_function="setRouter",
        attacker_capability="arbitrary external caller",
        expected_impact="unauthorized router change",
        source_path=str(FIXTURE.resolve()),
        declaring_contract=contract_name,
        source_line=source_line,
        display_label=f"H-AUTH-{contract_name}-setRouter",
    )
    experiment = Experiment(
        experiment_id=f"X-H-AUTH-{contract_name}-setRouter",
        hypothesis_id=hypothesis.hypothesis_id,
        action="Call setRouter as a non-owner and compare router before and after.",
        discriminates=("unauthorized pre-existing router change", "revert or no change"),
        cost=1.0,
        planned_inputs=("address(0xCAFE)",),
        target_function="setRouter",
    )
    return generate_blind_authorization_test_from_experiment(
        hypothesis,
        experiment,
        "../fixtures/state_control/StateControlFixture.sol",
        contract_name,
        tmp_path / f"Generated{contract_name}AuthTest.t.sol",
        model,
    ).read_text(encoding="utf-8")


def test_unguarded_owner_governed_preexisting_state_change_is_supported(tmp_path: Path):
    generated = _generate("StateControlFixture", guarded=False, tmp_path=tmp_path)

    assert 'observedStateVariable = "router";' in generated
    assert "observedStateExistedBefore = true;" in generated
    assert "observedAuthorityModelGovernsState = true;" in generated
    assert "observedStateChanged = stateReadBeforeSucceeded && stateReadAfterSucceeded" in generated
    assert "Verdict.Supported;" in generated
    assert 'verdictReason = "unauthorized_preexisting_authority_governed_state_changed";' in generated
    assert '"CYDRA_OBS_STATE_VARIABLE"' in generated
    assert '"CYDRA_OBS_STATE_EXISTED_BEFORE"' in generated
    assert '"CYDRA_OBS_AUTHORITY_MODEL_GOVERNS_STATE"' in generated
    assert '"CYDRA_OBS_STATE_CHANGED"' in generated


def test_only_owner_guarded_state_change_is_rejected_on_revert(tmp_path: Path):
    generated = _generate("GuardedStateControlFixture", guarded=True, tmp_path=tmp_path)

    assert "observedStateExistedBefore = true;" in generated
    assert "observedAuthorityModelGovernsState = false;" in generated
    assert 'verdictReason = "guarded_function_reverted";' in generated
    assert "Verdict.Supported;" in generated
