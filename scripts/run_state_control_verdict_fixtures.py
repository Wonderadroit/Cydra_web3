from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    {
        "label": "dcnteth-style-positive",
        "source": ROOT / "tests/fixtures/state_control/StateControlFixture.sol",
        "contract": "StateControlFixture",
        "function": "setRouter",
        "writes": ("router",),
        "parameter": ParameterModel(name="nextRouter", type="address"),
        "expected_verdict": 1,
        "expected_reason": "unauthorized_preexisting_authority_governed_state_changed",
        "expected_state_exists": "true",
        "expected_state_governed": "true",
    },
    {
        "label": "transfer-guard-factory-negative",
        "source": ROOT / "tests/fixtures/permissionless_factory/PermissionlessFactory.sol",
        "contract": "TransferGuardFactory",
        "function": "createTransferGuard",
        "writes": ("_isTransferGuard",),
        "parameter": None,
        "expected_verdict": 4,
        "expected_reason": "no_authority_getter",
        "expected_state_exists": "false",
        "expected_state_governed": "false",
    },
    {
        "label": "only-owner-guarded-negative",
        "source": ROOT / "tests/fixtures/state_control/StateControlFixture.sol",
        "contract": "GuardedStateControlFixture",
        "function": "setRouter",
        "writes": ("router",),
        "parameter": ParameterModel(name="nextRouter", type="address"),
        "expected_verdict": 2,
        "expected_reason": "guarded_function_reverted",
        "expected_state_exists": "true",
        "expected_state_governed": "false",
    },
)


def _run_fixture(fixture: dict) -> None:
    source_path = fixture["source"]
    source_text = source_path.read_text(encoding="utf-8")
    source_line = next(
        number for number, line in enumerate(source_text.splitlines(), start=1)
        if f"function {fixture['function']}(" in line
    )
    parameters = (fixture["parameter"],) if fixture["parameter"] else ()
    function = FunctionModel(
        name=fixture["function"],
        visibility="external",
        modifiers=("onlyOwner",) if fixture["label"] == "only-owner-guarded-negative" else (),
        writes=fixture["writes"],
        external_calls=(),
        line=source_line,
        parameters=parameters,
        source=str(source_path.resolve()),
    )
    model = ContractModel(
        name=fixture["contract"],
        source=str(source_path.resolve()),
        pragma="^0.8.22",
        state_variables=fixture["writes"],
        functions=(function,),
    )
    hypothesis_id = f"H-AUTH-{fixture['label']}"
    hypothesis = Hypothesis(
        hypothesis_id=hypothesis_id,
        claim="An unauthorized caller may change protected state.",
        invariant_id="INV-AUTH-001",
        target_function=fixture["function"],
        attacker_capability="arbitrary external caller",
        expected_impact="unauthorized state control",
        source_path=str(source_path.resolve()),
        declaring_contract=fixture["contract"],
        source_line=source_line,
        display_label=hypothesis_id,
    )
    planned_inputs = ("address(0xCAFE)",) if fixture["parameter"] else ()
    experiment = Experiment(
        experiment_id=f"X-{hypothesis_id}",
        hypothesis_id=hypothesis_id,
        action=f"Call {fixture['function']} as an unrelated caller and observe state.",
        discriminates=("unauthorized state change", "revert or no pre-existing governed state change"),
        cost=1.0,
        planned_inputs=planned_inputs,
        target_function=fixture["function"],
    )

    with tempfile.TemporaryDirectory(prefix=f"cydra-{fixture['label']}-") as temp:
        project = Path(temp)
        (project / "test").mkdir()
        relative_fixture = Path("fixtures") / fixture["source"].parent.name / fixture["source"].name
        destination = project / relative_fixture
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        (project / "foundry.toml").write_text(
            '[profile.default]\nsrc = "fixtures"\ntest = "test"\nout = "out"\nlibs = []\nsolc_version = "0.8.22"\n',
            encoding="utf-8",
        )
        generated = project / "test" / "GeneratedAuthorizationVerdict.t.sol"
        target_import = "../" + relative_fixture.as_posix()
        generate_blind_authorization_test_from_experiment(
            hypothesis,
            experiment,
            target_import,
            fixture["contract"],
            generated,
            model,
        )
        completed = subprocess.run(
            ["forge", "test", "--root", str(project), "-vvv"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=240,
            check=False,
        )
        output = completed.stdout
        expected_markers = (
            f"CYDRA_VERDICT {fixture['expected_verdict']}",
            f"CYDRA_VERDICT_REASON {fixture['expected_reason']}",
            f"CYDRA_OBS_STATE_EXISTED_BEFORE {fixture['expected_state_exists']}",
            f"CYDRA_OBS_AUTHORITY_MODEL_GOVERNS_STATE {fixture['expected_state_governed']}",
        )
        missing = [marker for marker in expected_markers if marker not in output]
        print(f"FIXTURE {fixture['label']} expected={fixture['expected_verdict']} exit={completed.returncode}")
        for marker in expected_markers:
            print(f"  {'OK' if marker in output else 'MISSING'} {marker}")
        if completed.returncode != 0 or missing:
            print(output)
            raise SystemExit(
                f"state-control fixture failed: {fixture['label']}; missing={missing!r}"
            )


def main() -> int:
    for fixture in FIXTURES:
        _run_fixture(fixture)
    print("STATE_CONTROL_FIXTURE_GATE PASS (3/3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
