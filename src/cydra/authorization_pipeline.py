from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from .ast_dataflow import SemanticRelationshipEvidence
from .models import ContractModel, Experiment, FunctionModel, Hypothesis, Invariant
from .hypothesis_seeds import HypothesisSeed, generate_hypothesis_seeds
from .reasoning import generate_access_control_hypotheses, plan_access_control_experiment
from .solidity_model import _strip_comments, parse_solidity


@dataclass(frozen=True)
class DerivedWriteEvidence:
    contract: str
    function: str
    state: str
    via_function: str
    source: str
    source_line: int


@dataclass(frozen=True)
class AuthorizationInvestigation:
    target: str
    contracts: tuple[ContractModel, ...]
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]
    experiments: tuple[Experiment, ...]
    status: str
    derived_effects: tuple[DerivedWriteEvidence, ...] = ()
    seeds: tuple[HypothesisSeed, ...] = ()
    outcome_records: tuple[dict[str, object], ...] = ()


_FUNCTION_RE = re.compile(r"\bfunction\s+(?P<name>[A-Za-z_]\w*)\s*\(")
_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")


def _function_body(source: str, function: FunctionModel) -> str:
    """Extract a body by source line; declarations without bodies return empty."""
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") != function.name:
            continue
        if source.count("\n", 0, match.start()) + 1 != function.line:
            continue
        opening = source.find("{", match.end())
        semicolon = source.find(";", match.end())
        if opening < 0 or (semicolon >= 0 and semicolon < opening):
            return ""
        depth = 1
        for index in range(opening + 1, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[opening + 1:index]
        return ""
    return ""


def _with_transitive_internal_writes(
    contract: ContractModel,
    source_path: Path,
) -> tuple[ContractModel, tuple[DerivedWriteEvidence, ...]]:
    """Propagate writes through same-contract internal calls without guessing targets."""
    try:
        source = _strip_comments(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return contract, ()

    functions = contract.functions
    keys = tuple((item.name, item.line) for item in functions)
    by_name: dict[str, list[tuple[str, int]]] = {}
    direct: dict[tuple[str, int], set[str]] = {}
    bodies: dict[tuple[str, int], str] = {}
    for item, key in zip(functions, keys):
        by_name.setdefault(item.name, []).append(key)
        direct[key] = set(item.writes)
        bodies[key] = _function_body(source, item)

    known_names = set(by_name)
    calls: dict[tuple[str, int], set[str]] = {}
    for key, body in bodies.items():
        calls[key] = {
            match.group(1)
            for match in _CALL_RE.finditer(body)
            if match.group(1) in known_names
        }

    effective = {key: set(writes) for key, writes in direct.items()}
    # A finite monotone union reaches a fixed point even when helpers call each other.
    for _ in range(len(functions) + 1):
        changed = False
        for key in keys:
            for callee_name in calls[key]:
                for callee_key in by_name.get(callee_name, ()):
                    before = len(effective[key])
                    effective[key].update(effective[callee_key])
                    changed = changed or len(effective[key]) != before
        if not changed:
            break

    derived: list[DerivedWriteEvidence] = []
    enriched: list[FunctionModel] = []
    for item, key in zip(functions, keys):
        enriched.append(replace(item, writes=tuple(sorted(effective[key]))))
        for state in sorted(effective[key] - direct[key]):
            via = next(
                (
                    name for name in sorted(calls[key])
                    if any(state in effective[callee_key] for callee_key in by_name.get(name, ()))
                ),
                "internal-call-closure",
            )
            derived.append(DerivedWriteEvidence(
                contract=contract.name,
                function=item.name,
                state=state,
                via_function=via,
                source=str(source_path),
                source_line=item.line,
            ))

    return replace(contract, functions=tuple(enriched)), tuple(derived)


def investigate_authorization(
    source: str | Path,
    *,
    target: str | None = None,
    semantic_evidence: tuple[SemanticRelationshipEvidence, ...] = (),
) -> AuthorizationInvestigation:
    """Run only the authorization hypothesis path; do not invoke other bug classes.

    The model includes direct and same-contract helper-mediated state writes. This is
    hypothesis-generation evidence only: all candidates still require execution and
    causal verification before any vulnerability can be claimed.
    """
    source_path = Path(source).resolve()
    parsed = parse_solidity(source_path)
    modeled: list[ContractModel] = []
    derived: list[DerivedWriteEvidence] = []
    for contract in parsed:
        enriched, effects = _with_transitive_internal_writes(contract, source_path)
        modeled.append(enriched)
        derived.extend(effects)

    # Derive one explicit outcome per seed, bound by the full source identity tuple.
    seeds = generate_hypothesis_seeds(tuple(modeled))
    proposed = tuple(hypothesis for contract in modeled for hypothesis in generate_access_control_hypotheses(contract, semantic_evidence))
    by_identity = {(str(Path(item.source_path or "").resolve()), item.declaring_contract, item.target_function, item.source_line): item for item in proposed}
    outcomes: list[dict[str, object]] = []
    linked: list[Hypothesis] = []
    for seed in seeds:
        identity = (str(Path(seed.source).resolve()), seed.target_contract, seed.target_function, seed.source_line)
        hypothesis = by_identity.get(identity)
        if hypothesis is not None:
            hypothesis = replace(hypothesis, originating_seed_id=seed.seed_id)
            linked.append(hypothesis)
            outcomes.append({"seed_id": seed.seed_id, "source_path": identity[0], "declaring_contract": identity[1], "function_name": identity[2], "source_line": identity[3], "outcome": "hypothesis", "hypothesis_id": hypothesis.hypothesis_id, "originating_seed_id": seed.seed_id})
            continue
        contract = next((item for item in modeled if item.name == seed.target_contract and str(Path(item.source).resolve()) == identity[0]), None)
        function = next((item for item in contract.functions if item.name == seed.target_function and item.line == seed.source_line), None) if contract else None
        if seed.status == "blocked" and seed.target_function.lower().startswith(("initialize", "initialise", "init")):
            reason = "blocked:lifecycle"
        elif function is not None and function.modifiers:
            reason = "filtered:modifier-authorization"
        elif function is None or function.visibility not in {"public", "external"}:
            reason = "rejected:not-authorized-surface"
        else:
            reason = "candidate-mismatch"
        outcomes.append({"seed_id": seed.seed_id, "source_path": identity[0], "declaring_contract": identity[1], "function_name": identity[2], "source_line": identity[3], "outcome": "non_transition", "reason_code": reason})
    ordered = tuple(sorted(linked, key=lambda item: item.hypothesis_id))
    experiments = tuple(plan_access_control_experiment(item) for item in ordered)
    invariant = (Invariant(
        "INV-AUTH-001",
        "Externally callable operations that mutate privileged state must enforce the target's authorization boundary.",
        "authorization specialist invariant; generated candidates require semantic and execution validation",
        0.90,
    ),)
    return AuthorizationInvestigation(
        target=target or str(source_path),
        contracts=tuple(modeled),
        invariants=invariant,
        hypotheses=ordered,
        experiments=experiments,
        status="HYPOTHESES_READY" if ordered else "NO_AUTH_HYPOTHESIS",
        derived_effects=tuple(derived),
        seeds=seeds,
        outcome_records=tuple(outcomes),
    )
