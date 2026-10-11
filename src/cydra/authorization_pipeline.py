from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ast_dataflow import SemanticRelationshipEvidence
from .models import ContractModel, Experiment, Hypothesis, Invariant
from .reasoning import generate_access_control_hypotheses, plan_access_control_experiment
from .solidity_model import parse_solidity


@dataclass(frozen=True)
class AuthorizationInvestigation:
    target: str
    contracts: tuple[ContractModel, ...]
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]
    experiments: tuple[Experiment, ...]
    status: str


def investigate_authorization(
    source: str | Path,
    *,
    target: str | None = None,
    semantic_evidence: tuple[SemanticRelationshipEvidence, ...] = (),
) -> AuthorizationInvestigation:
    """Run only the authorization hypothesis path; do not invoke other bug classes.

    This is a source-modeling stage, not a finding engine. Hypotheses produced here
    must be executed and causally verified before any vulnerability can be claimed.
    """
    source_path = Path(source).resolve()
    contracts = parse_solidity(source_path)
    hypotheses: list[Hypothesis] = []
    for contract in contracts:
        hypotheses.extend(generate_access_control_hypotheses(contract, semantic_evidence))
    unique = {item.hypothesis_id: item for item in hypotheses}
    ordered = tuple(unique[key] for key in sorted(unique))
    experiments = tuple(plan_access_control_experiment(item) for item in ordered)
    invariant = ()
    if ordered:
        invariant = (Invariant(
            "INV-AUTH-001",
            "Externally callable operations that mutate privileged state must enforce the target's authorization boundary.",
            "authorization specialist invariant; generated candidates require semantic and execution validation",
            0.90,
        ),)
    return AuthorizationInvestigation(
        target=target or str(source_path),
        contracts=contracts,
        invariants=invariant,
        hypotheses=ordered,
        experiments=experiments,
        status="HYPOTHESES_READY" if ordered else "NO_AUTH_HYPOTHESIS",
    )
