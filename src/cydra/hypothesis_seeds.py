from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Literal

from .models import ContractModel, FunctionModel
from .reasoning import modifier_restriction_category

SeedStatus = Literal["seed", "testable", "blocked"]
InvariantSource = Literal["derived", "generic"]
ANALYSIS_BUDGET = "direct-call-sites; one-inheritance-level; no-cross-contract-resolution"


@dataclass(frozen=True)
class HypothesisSeed:
    """A provisional, provenance-linked security question, not a finding."""
    seed_id: str
    target_contract: str
    target_function: str
    question: str
    invariant: str
    invariant_source: InvariantSource
    falsification: str
    preconditions_needed: tuple[str, ...]
    status: SeedStatus
    source: str
    source_line: int
    observed_writes: tuple[str, ...]
    provenance: tuple[str, ...]
    uncertainty: tuple[str, ...]
    analysis_budget: str = ANALYSIS_BUDGET


def _is_lifecycle_surface(contract: ContractModel, function: FunctionModel) -> bool:
    name = function.name.lower()
    modifiers = function.modifiers
    return (
        name.startswith(("initialize", "initialise", "init", "reinitialize", "reinitialise"))
        or any(
            modifier_restriction_category(contract, function, modifier) == "lifecycle"
            for modifier in modifiers
        )
    )

def _function_body(function: FunctionModel, contract: ContractModel) -> str | None:
    try:
        source = Path(function.source or contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    pattern = re.compile(
        r"\bfunction\s+" + re.escape(function.name) + r"\s*\([^)]*\)[^{;]*\{",
        re.MULTILINE,
    )
    match = pattern.search(source)
    if not match:
        return None
    depth = 1
    end = match.end()
    while end < len(source) and depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[match.end():end - 1] if depth == 0 else None


def _observed_writes(contract: ContractModel, function: FunctionModel) -> tuple[str, ...]:
    if function.writes:
        return tuple(function.writes)
    body = _function_body(function, contract)
    if body is None:
        return ()
    writes = [
        name for name in contract.state_variables
        if re.search(r"\b" + re.escape(name) + r"\b(?:\s*\[[^]]*\])*\s*(?:=(?!=)|\+=|-=|\*=|/=|\+\+|--)", body)
    ]
    return tuple(sorted(set(writes)))


def _unresolved_execution_path(
    contract: ContractModel, function: FunctionModel
) -> tuple[str, ...]:
    """Return provenance for direct call sites not classifiable within the fixed budget.

    This is not a resolver. A local/helper call is classified only when the model
    has that callee and it exposes writes or authorization. Inheritance is limited
    to one modeled level; cross-contract calls remain unresolved by definition.
    """
    body = _function_body(function, contract)
    if function.body_scope == "out_of_scope":
        return (f"inherited_body_out_of_scope:{function.source or contract.source}::{function.name}",)
    if body is None:
        return (f"source_body_unavailable:{function.source or contract.source}::{function.name}",) + tuple(
            f"model_call:{call}:source_body_unavailable" for call in function.external_calls
        )

    unresolved: list[str] = []
    local = {item.name: item for item in contract.functions}
    inherited = {item.name: item for item in contract.inherited_functions}
    for match in re.finditer(r"\bsuper\.(\w+)\s*\(", body):
        name = match.group(1)
        callee = inherited.get(name)
        if callee is None or callee.body_scope == "out_of_scope" or not (
            callee.writes or callee.modifiers or callee.authorization_predicates
        ):
            source = callee.source if callee is not None and callee.source else contract.source
            unresolved.append(f"super.{name}:inherited_body_out_of_scope:{source}::{name}")

    excluded = {
        "require", "assert", "revert", "if", "while", "for", "return", "emit",
        "keccak256", "abi", "address", "bytes", "uint", "int", "string", "bool",
    }
    for match in re.finditer(r"(?<![.\w])([A-Za-z_]\w*)\s*\(", body):
        name = match.group(1)
        if name in excluded or name == function.name:
            continue
        callee = local.get(name) or inherited.get(name)
        if callee is None:
            continue
        if not (callee.writes or callee.modifiers or callee.authorization_predicates):
            unresolved.append(f"{name}:callee_effect_or_authorization_unclassified")

    for match in re.finditer(r"\b(delegatecall|staticcall)\s*\(|\.call\s*(?:\{|\()", body):
        unresolved.append(f"{match.group(0).strip()}:cross_contract_or_low_level_effect_unresolved")

    known_names = set(local) | set(inherited)
    for call in function.external_calls:
        # The parser represents some call sites as (receiver, method) pairs.
        if isinstance(call, (tuple, list)):
            call_name = str(call[-1]).split("(", 1)[0].strip() if call else ""
            receiver = str(call[0]) if len(call) > 1 else ""
        else:
            call_name = str(call).rsplit(".", 1)[-1].split("(", 1)[0].strip()
            receiver = ""
        if not call_name:
            continue
        callee = local.get(call_name) or inherited.get(call_name)
        classified = bool(
            callee
            and (
                callee.writes
                or callee.modifiers
                or callee.authorization_predicates
                or callee.state_predicates
                or callee.return_expressions
            )
        )
        if call_name not in known_names or not classified:
            prefix = receiver + "." if receiver else ""
            unresolved.append(f"model_call:{prefix}{call_name}:callee_effect_or_authorization_unclassified")

    return tuple(dict.fromkeys(unresolved))


def generate_hypothesis_seeds(contracts: tuple[ContractModel, ...] | list[ContractModel]) -> tuple[HypothesisSeed, ...]:
    """Emit provisional questions from writes or unresolved execution paths."""
    seeds: list[HypothesisSeed] = []
    for contract in contracts:
        for function in contract.functions:
            if function.visibility not in {"public", "external"}:
                continue
            observed_writes = _observed_writes(contract, function)
            lifecycle = _is_lifecycle_surface(contract, function)
            unresolved = _unresolved_execution_path(contract, function)
            if not observed_writes and not lifecycle and not unresolved:
                continue

            source = function.source or contract.source
            if function.body_scope == "out_of_scope":
                question = f"Can a caller outside the evidenced trust boundary trigger security-relevant effects through inherited {function.name}?"
                invariant = "Execution with security-relevant effects must be restricted to actors authorized by the target's evidenced trust boundary."
                invariant_source: InvariantSource = "generic"
                prerequisites = ("analyze_inherited_body", "intended_authorization_boundary", "deployment_or_local_fork")
                status: SeedStatus = "blocked"
                uncertainty = (
                    "inherited body is retained as surface context but is outside the analyzed source scope",
                    "the effective authorization boundary and runtime reachability are not established",
                )
            elif lifecycle:
                writes = ", ".join(observed_writes) if observed_writes else "lifecycle-sensitive state"
                question = f"Can a caller outside the intended trust boundary change {writes} through {function.name} in a reachable deployment state?"
                invariant = f"Only an actor authorized by the evidenced trust boundary may change security-relevant state ({writes})."
                invariant_source: InvariantSource = "derived" if observed_writes else "generic"
                prerequisites = ("deployment_evidence", "initialization_state", "proxy_or_deployment_context")
                status: SeedStatus = "blocked"
                uncertainty = (
                    "deployment and proxy context are unknown from source modeling alone",
                    "initialization state is unknown",
                    "intended privileged actor must be established from target evidence",
                )
            elif observed_writes:
                writes = ", ".join(observed_writes)
                question = f"Can a caller outside the intended trust boundary change {writes} through {function.name}?"
                invariant = f"Only an actor authorized by the evidenced trust boundary may change security-relevant state ({writes})."
                invariant_source = "derived"
                prerequisites = ("deployment_or_local_fork", "intended_authorization_boundary", "control_actor_setup")
                status = "seed"
                uncertainty = (
                    "source-level writes do not establish runtime reachability",
                    "effective inherited/helper guards require validation",
                )
            else:
                question = (
                    f"Can a caller outside the evidenced trust boundary trigger security-relevant "
                    f"effects through {function.name} along the unresolved execution path?"
                )
                invariant = "Execution with security-relevant effects must be restricted to actors authorized by the target's evidenced trust boundary."
                invariant_source = "generic"
                prerequisites = ("resolve_recorded_execution_path", "intended_authorization_boundary", "deployment_or_local_fork")
                status = "blocked"
                uncertainty = (
                    "security-relevant effects and/or authorization along the recorded path are not established within the analysis budget",
                    "no target-specific authorization semantics are assumed",
                )

            seeds.append(HypothesisSeed(
                seed_id=f"SEED-AUTH-{function.declaring_contract or contract.name}-{function.name}-{function.line}",
                target_contract=function.declaring_contract or contract.name,
                target_function=function.name,
                question=question,
                invariant=invariant,
                invariant_source=invariant_source,
                falsification=(
                    f"Under documented preconditions, a caller outside the evidenced trust boundary "
                    f"changes the questioned state or causes an execution effect through {function.name}; "
                    "compare against a protected control."
                ),
                preconditions_needed=prerequisites,
                status=status,
                source=source,
                source_line=function.line,
                observed_writes=observed_writes,
                provenance=tuple(
                    [f"source:{source}:{function.line}"]
                    + [f"observed_write:{name}" for name in observed_writes]
                    + [f"unresolved_path:{item}" for item in unresolved]
                ),
                uncertainty=uncertainty,
            ))
    return tuple(seeds)


def seeds_as_dicts(seeds: tuple[HypothesisSeed, ...]) -> list[dict[str, object]]:
    """Return stable JSON-ready records for campaign artifacts."""
    return [asdict(seed) for seed in seeds]
