from pathlib import Path

import pytest

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis


def _case(tmp_path: Path, *, kind="contract", unimplemented=False, body_complete=True):
    source = tmp_path / "Target.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Target { uint public value; function setValue(uint v) external { value = v; } }",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="setValue", visibility="external", modifiers=(), writes=("value",),
        external_calls=(), line=1, source=str(source),
    )
    model = ContractModel(
        name="Target", source=str(source), functions=(function,),
        contract_kind=kind, has_unimplemented_functions=unimplemented,
        function_body_metadata_complete=body_complete,
    )
    hypothesis = Hypothesis(
        hypothesis_id="H-AUTH-TEST", claim="unauthorized caller cannot mutate value",
        invariant_id="INV-AUTH-001", target_function="setValue",
        attacker_capability="unprivileged caller", expected_impact="unauthorized state mutation",
    )
    experiment = Experiment(
        experiment_id="E-AUTH-TEST", hypothesis_id=hypothesis.hypothesis_id,
        action="call setValue", discriminates=("authorized", "unauthorized"), cost=1.0,
    )
    return model, hypothesis, experiment, source


@pytest.mark.parametrize(
    ("kind", "unimplemented", "body_complete", "reason"),
    [
        ("contract", True, True, "not_deployable:abstract"),
        ("interface", False, True, "not_deployable:interface"),
        ("library", False, True, "out_of_scope:library"),
        (None, False, True, "ast_metadata_missing"),
        ("contract", False, None, "ast_metadata_incomplete"),
    ],
)
def test_deployment_generator_fails_closed_with_reason(
    tmp_path, kind, unimplemented, body_complete, reason
):
    model, hypothesis, experiment, source = _case(
        tmp_path, kind=kind, unimplemented=unimplemented, body_complete=body_complete
    )
    with pytest.raises(ValueError, match=reason):
        generate_blind_authorization_test_from_experiment(
            hypothesis, experiment, "Target.sol", "Target",
            tmp_path / "generated.t.sol", model,
        )


def test_concrete_contract_generates_real_creation_code(tmp_path):
    model, hypothesis, experiment, source = _case(tmp_path)
    output = generate_blind_authorization_test_from_experiment(
        hypothesis, experiment, "Target.sol", "Target",
        tmp_path / "generated.t.sol", model,
    )
    generated = output.read_text(encoding="utf-8")
    assert "type(Target).creationCode" in generated
    assert "new Target(" not in generated
