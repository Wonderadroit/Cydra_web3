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
    verdict: str


def _security_assertion_failed(execution: ExecutionResult) -> bool:
    output = f"{execution.stdout}\n{execution.stderr}"
    return _SECURITY_MARKER in output and execution.status == "FAIL"


def classify_authorization_blind_execution(
    hypothesis: Hypothesis,
    execution: ExecutionResult,
) -> AuthorizationBlindOutcome:
    """Classify the generated harness's state-backed verdict, not test pass/fail."""
    evidence_id = f"E-EXEC-{hypothesis.hypothesis_id}-AUTHORIZATION-BLIND"
    output = f"{execution.stdout}\n{execution.stderr}"
    labels = {
        "0": "none",
        "1": "supported",
        "2": "rejected",
        "3": "inconclusive",
        "4": "unmeasurable",
    }
    matches = re.findall(
        r"CYDRA_VERDICT[:\s]+(supported|rejected|inconclusive|unmeasurable|[0-4])",
        output,
        re.IGNORECASE,
    )
    raw_verdict = matches[-1].lower() if matches else None
    verdict = labels.get(raw_verdict, raw_verdict) if raw_verdict is not None else None

    if verdict == "supported":
        semantics = "unauthorized_authority_gain"
        internal_status, benchmark_status = "confirmed", "confirmed"
    elif verdict == "rejected":
        semantics = "authority_gain_not_observed"
        internal_status, benchmark_status = "rejected", "not_confirmed"
    elif verdict == "inconclusive":
        semantics = "experiment_inconclusive"
        internal_status, benchmark_status = "proposed", "inconclusive"
    elif verdict == "unmeasurable":
        semantics = "authority_delta_unmeasurable"
        internal_status, benchmark_status = "proposed", "unmeasurable"
    elif execution.status == "UNMEASURABLE" or not execution.executed:
        verdict = "unmeasurable"
        semantics = "harness_not_executed"
        internal_status, benchmark_status = "proposed", "unmeasurable"
    elif execution.status == "FAIL":
        verdict = "inconclusive"
        semantics = "execution_failed_without_verdict"
        internal_status, benchmark_status = "proposed", "inconclusive"
    else:
        verdict = "inconclusive"
        semantics = "runtime_verdict_missing"
        internal_status, benchmark_status = "proposed", "inconclusive"

    evidence = Evidence(
        evidence_id,
        "execution",
        (
            f"Blind authorization experiment: verdict={verdict}, semantics={semantics}, "
            f"status={execution.status}, executed={execution.executed}, "
            f"tests_run={execution.tests_run}, tests_failed={execution.tests_failed}, "
            f"exit={execution.exit_code}."
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
        updated, execution, evidence, internal_status, benchmark_status, verdict
    )

