from __future__ import annotations

from dataclasses import dataclass
import re

from .foundry import ExecutionResult
from .models import Evidence, Hypothesis


_SECURITY_MARKER = "CYDRA_SECURITY_ASSERTION"


@dataclass(frozen=True)
class AuthorizationBlindOutcome:
    hypothesis: Hypothesis
    execution: ExecutionResult
    evidence: Evidence
    internal_status: str
    benchmark_status: str
    measurement_verdict: str


def _security_assertion_failed(execution: ExecutionResult) -> bool:
    output = f"{execution.stdout}\n{execution.stderr}"
    return _SECURITY_MARKER in output and execution.status == "FAIL"


def _measurement_assertion_failed(execution: ExecutionResult) -> bool:
    output = f"{execution.stdout}\n{execution.stderr}"
    return "CYDRA_MEASUREMENT_ASSERTION:" in output and execution.status == "FAIL"


def classify_authorization_blind_execution(
    hypothesis: Hypothesis,
    execution: ExecutionResult,
) -> AuthorizationBlindOutcome:
    """Classify differential evidence as supported, rejected, or unmeasurable.

    A passing generated harness proves that the authorized caller changed observed
    state while the unauthorized caller reverted without changing it. Only the
    explicit unauthorized-mutation assertion supports a positive finding.
    """
    evidence_id = f"E-EXEC-{hypothesis.hypothesis_id}-AUTHORIZATION-BLIND"
    if execution.status == "UNMEASURABLE" or not execution.executed:
        semantics = "unmeasurable"
        measurement_verdict = "unmeasurable"
        internal_status = benchmark_status = "proposed"
    elif execution.status == "PASS":
        # A passing differential harness has established both controls:
        # authorized caller changed observed state; unauthorized caller reverted
        # without changing it.
        semantics = "authorized_control_succeeded_unauthorized_control_rejected"
        measurement_verdict = "rejected"
        internal_status, benchmark_status = "rejected", "not_confirmed"
    elif _security_assertion_failed(execution):
        semantics = "unauthorized_state_mutation"
        measurement_verdict = "supported"
        internal_status = benchmark_status = "confirmed"
    elif _measurement_assertion_failed(execution):
        semantics = "differential_control_not_established"
        measurement_verdict = "unmeasurable"
        internal_status = benchmark_status = "proposed"
    else:
        semantics = "non_security_execution_failure"
        measurement_verdict = "unmeasurable"
        internal_status = benchmark_status = "proposed"

    evidence = Evidence(
        evidence_id,
        "execution",
        (
            f"Authorization differential: verdict={measurement_verdict}, "
            f"semantics={semantics}, status={execution.status}, "
            f"executed={execution.executed}, tests_run={execution.tests_run}, "
            f"tests_failed={execution.tests_failed}, exit={execution.exit_code}."
        ),
        " ".join(execution.command),
        execution.target + ".t.sol",
    )
    updated = Hypothesis(
        hypothesis.hypothesis_id,
        hypothesis.claim,
        hypothesis.invariant_id,
        hypothesis.target_function,
        hypothesis.attacker_capability,
        hypothesis.expected_impact,
        internal_status,
        hypothesis.evidence_ids + (evidence_id,),
        hypothesis.related_functions,
    )
    return AuthorizationBlindOutcome(
        updated, execution, evidence, internal_status, benchmark_status, measurement_verdict
    )


def security_assertion_marker() -> str:
    return _SECURITY_MARKER
