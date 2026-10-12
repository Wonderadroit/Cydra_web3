from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.foundry import ExecutionResult
from cydra.models import Hypothesis


def _hypothesis():
    return Hypothesis(
        hypothesis_id="H-VERDICT-CLASSIFIER",
        claim="runtime verdict classifier must preserve all four outcomes",
        invariant_id="INV-AUTH-001",
        target_function="setTarget",
        attacker_capability="arbitrary caller",
        expected_impact="authority gain",
    )


def _execution(label: str, *, status: str = "PASS", executed: bool = True):
    return ExecutionResult(
        experiment_id="X-VERDICT-CLASSIFIER",
        target="fixture",
        command=("forge", "test"),
        exit_code=0 if status == "PASS" else 1,
        executed=executed,
        tests_run=1 if executed else 0,
        tests_failed=0 if status == "PASS" else 1,
        status=status,
        stdout=f"CYDRA_VERDICT {label}",
        stderr="",
    )


def test_supported_runtime_verdict_is_not_inferred_from_test_pass():
    outcome = classify_authorization_blind_execution(_hypothesis(), _execution("1"))
    assert outcome.verdict == "supported"
    assert outcome.benchmark_status == "confirmed"


def test_rejected_runtime_verdict_is_distinct():
    outcome = classify_authorization_blind_execution(_hypothesis(), _execution("2"))
    assert outcome.verdict == "rejected"
    assert outcome.benchmark_status == "not_confirmed"


def test_inconclusive_runtime_verdict_is_not_rejected():
    outcome = classify_authorization_blind_execution(_hypothesis(), _execution("3"))
    assert outcome.verdict == "inconclusive"
    assert outcome.benchmark_status == "inconclusive"


def test_unmeasurable_runtime_verdict_is_not_rejected():
    outcome = classify_authorization_blind_execution(_hypothesis(), _execution("4"))
    assert outcome.verdict == "unmeasurable"
    assert outcome.benchmark_status == "unmeasurable"


def test_missing_runtime_verdict_fails_closed_as_inconclusive():
    outcome = classify_authorization_blind_execution(_hypothesis(), _execution("none"))
    assert outcome.verdict == "inconclusive"
    assert outcome.benchmark_status == "inconclusive"
