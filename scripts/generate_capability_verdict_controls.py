from __future__ import annotations

import os
from pathlib import Path

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "tests/fixtures/capability_verdict_runtime"
OUTPUT = PROJECT / "test/generated"


def generate(name: str, source_relative: str, function_name: str, writes: tuple[str, ...], parameters=()):
    source = ROOT / source_relative
    model = ContractModel(
        name=name,
        source=str(source.resolve()),
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
                parameters=tuple(parameters),
                source=str(source.resolve()),
            ),
        ),
    )
    hypothesis = Hypothesis(
        hypothesis_id=f"H-VERDICT-{name}",
        claim=f"runtime capability delta for {name}.{function_name}",
        invariant_id="INV-AUTH-001",
        target_function=function_name,
        attacker_capability="arbitrary external caller",
        expected_impact="unauthorized authority gain",
    )
    experiment = Experiment(
        experiment_id=f"X-VERDICT-{name}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=f"Call {function_name} and measure authority before and after.",
        discriminates=("authority gain", "no authority gain", "unmeasurable"),
        cost=1.0,
        planned_inputs=("address(0xCAFE)",) if parameters else (),
        target_function=function_name,
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / f"Generated{name}VerdictTest.t.sol"
    import_path = os.path.relpath(source, destination.parent).replace(os.sep, "/")
    generate_blind_authorization_test_from_experiment(
        hypothesis,
        experiment,
        import_path,
        name,
        destination,
        model,
    )


def main():
    generate(
        "VulnerableAuthority",
        "tests/fixtures/vulnerable_authority/VulnerableAuthority.sol",
        "setTarget",
        ("target", "_roles"),
        (ParameterModel(name="newTarget", type="address"),),
    )
    generate(
        "PermissionlessFactory",
        "tests/fixtures/permissionless_factory/PermissionlessFactory.sol",
        "create",
        ("_isChild",),
    )
    generate(
        "GuardedAuthorityRuntime",
        "tests/fixtures/capability_verdict_runtime/src/GuardedAuthority.sol",
        "setTarget",
        ("_roles",),
        (ParameterModel(name="newTarget", type="address"),),
    )
    generate(
        "BrokenSetupRuntime",
        "tests/fixtures/capability_verdict_runtime/src/BrokenSetup.sol",
        "setTarget",
        (),
        (ParameterModel(name="newTarget", type="address"),),
    )
    print(f"Generated four runtime harnesses in {OUTPUT}")


if __name__ == "__main__":
    main()
