from pathlib import Path

import pytest

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis


@pytest.mark.xfail(
    strict=True,
    reason="Known capability-model gap; tracked in https://github.com/Wonderadroit/Cydra_web3/pull/42",
)
def test_permissionless_factory_registry_write_is_not_an_authorization_judgment(tmp_path: Path):
    """A fresh child registry entry is not evidence that the caller gained privilege."""
    fixture = Path(__file__).parent / "fixtures" / "permissionless_factory" / "PermissionlessFactory.sol"
    source = fixture.read_text(encoding="utf-8")

    # Keep the fixture's semantics explicit: the registry key is the fresh child
    # returned by new, and the only write is a record of that creation.
    assert "child = address(new PermissionlessChild())" in source
    assert "_isChild[child] = true" in source
    assert "function create() external" in source

    model = ContractModel(
        name="PermissionlessFactory",
        source=str(fixture.resolve()),
        pragma="^0.8.22",
        state_variables=("_isChild",),
        functions=(
            FunctionModel(
                name="create",
                visibility="external",
                modifiers=(),
                writes=("_isChild",),
                external_calls=(),
                line=10,
                parameters=(),
                source=str(fixture.resolve()),
            ),
        ),
    )
    hypothesis = Hypothesis(
        hypothesis_id="H-AUTH-create",
        claim="create may permit an unauthorized caller to mutate privileged state",
        invariant_id="INV-AUTH-001",
        target_function="create",
        attacker_capability="arbitrary external caller",
        expected_impact="privileged configuration or authorization state can be changed",
    )
    experiment = Experiment(
        experiment_id="X-H-AUTH-create",
        hypothesis_id=hypothesis.hypothesis_id,
        action="Call create as an unrelated actor and compare security-relevant capabilities before and after.",
        discriminates=(
            "caller gains authority over a pre-existing resource",
            "caller only creates a new resource and its own registry entry",
        ),
        cost=1.0,
        target_function="create",
    )
    generated = generate_blind_authorization_test_from_experiment(
        hypothesis,
        experiment,
        "../fixtures/permissionless_factory/PermissionlessFactory.sol",
        "PermissionlessFactory",
        tmp_path / "GeneratedFactoryAuthTest.t.sol",
        model,
    ).read_text(encoding="utf-8")

    # Fail closed: success of a permissionless create() must not itself be
    # emitted as a security assertion. The assertion must compare capability
    # or authority over pre-existing resources, not merely require call failure.
    assert "CYDRA_SECURITY_ASSERTION" not in generated, (
        "false-positive calibration failure: generated test treats permissionless "
        "factory creation as proof of unauthorized privilege gain"
    )
    assert "require(\\n            !ok" not in generated
