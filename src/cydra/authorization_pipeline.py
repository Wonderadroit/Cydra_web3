from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from .ast_dataflow import SemanticRelationshipEvidence
from .models import ContractModel, Experiment, FunctionModel, Hypothesis, Invariant
from .hypothesis_seeds import HypothesisSeed, generate_hypothesis_seeds
from .reasoning import _effective_declared_modifiers, _modifier_body_enforces_authorization, generate_access_control_hypotheses, plan_access_control_experiment
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


def _hypotheses_from_derived_write_seeds(
    seeds: tuple[HypothesisSeed, ...],
    existing: tuple[Hypothesis, ...],
    protected_targets: set[tuple[str, str]] | None = None,
) -> tuple[Hypothesis, ...]:
    """Promote source-derived write seeds into falsifiable candidates.

    This is a coverage fallback, not a finding: candidates still require execution,
    causal verification, and reproduction. Generic unresolved-path and lifecycle
    seeds remain blocked and are deliberately not promoted here.
    """
    existing_functions = {item.target_function for item in existing}
    protected_targets = protected_targets or set()
    candidates: list[Hypothesis] = []
    for seed in seeds:
        if (
            seed.status != "seed"
            or seed.invariant_source != "derived"
            or not seed.observed_writes
            or (seed.target_contract, seed.target_function) in protected_targets
            or seed.target_function in existing_functions
        ):
            continue
        writes = ", ".join(seed.observed_writes)
        candidates.append(Hypothesis(
            hypothesis_id=f"H-AUTH-SEED-{seed.target_contract}-{seed.target_function}-{seed.source_line}",
            claim=seed.question,
            invariant_id="INV-AUTH-001",
            target_function=seed.target_function,
            attacker_capability="caller outside the evidenced trust boundary",
            expected_impact=f"security-relevant state may be changed: {writes}",
            evidence_ids=(f"E-SEED-{seed.seed_id}",),
        ))
        existing_functions.add(seed.target_function)
    return tuple(candidates)


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

    # Seeds are a separate pre-proof artifact; do not derive their existence from
    # whether the narrower exploit-candidate filter emits a hypothesis.
    seeds = generate_hypothesis_seeds(tuple(modeled))

    hypotheses: list[Hypothesis] = []
    for contract in modeled:
        hypotheses.extend(generate_access_control_hypotheses(contract, semantic_evidence))
    conventional = tuple(hypotheses)
    protected_targets = {
        (contract.name, function.name)
        for contract in modeled
        for function in contract.functions
        if any(
            _modifier_body_enforces_authorization(contract, modifier)
            for modifier in _effective_declared_modifiers(contract, function)
        )
    }
    hypotheses.extend(_hypotheses_from_derived_write_seeds(seeds, conventional, protected_targets))
    unique = {item.hypothesis_id: item for item in hypotheses}
    ordered = tuple(unique[key] for key in sorted(unique))
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
    )
