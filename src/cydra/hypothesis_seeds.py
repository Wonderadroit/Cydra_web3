from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Literal

from .models import ContractModel, FunctionModel

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


def _is_lifecycle_surface(function: FunctionModel) -> bool:
    name = function.name.lower()
    modifiers = {item.lower() for item in function.modifiers}
    return (
        name.startswith(("initialize", "initialise", "init", "reinitialize", "reinitialise"))
        or "initializer" in modifiers
        or any(item.startswith("reinitializer") for item in modifiers)
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


def _function_body(function: FunctionModel, contract: ContractModel) -> str | None:
    """Read the body for the declaration at its recorded line, including overloads."""
    try:
        source = Path(function.source or contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    pattern = re.compile(
        r"\\bfunction\\s+" + re.escape(function.name) + r"\\s*\\([^)]*\\)[^{;]*\\{",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(source))
    if not matches:
        return None
    match = min(matches, key=lambda item: abs(source.count("\\n", 0, item.start()) + 1 - function.line))
    opening = match.end() - 1
    depth = 1
    end = opening + 1
    while end < len(source) and depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[opening + 1:end - 1] if depth == 0 else None


def _bounded_callee_walk(
    contract: ContractModel, function: FunctionModel
) -> tuple[tuple[str, ...], tuple[str, ...], str | None, int]:
    """Resolve in-closure internal effects with source provenance and a measured budget.

    Returns (effect records, provenance records, blocker, measured_depth). Unknown
    dispatch is fail-closed. External Permit2/AllowanceHolder implementations are
    boundaries: their calls are recorded but never traversed.
    """
    local = tuple(contract.functions)
    inherited = tuple(contract.inherited_functions)
    available = (*local, *inherited)
    by_name: dict[str, list[FunctionModel]] = {}
    for item in available:
        by_name.setdefault(item.name, []).append(item)

    effects: list[str] = []
    provenance: list[str] = []
    blockers: list[str] = []
    max_depth = 0
    visited: set[tuple[str, str, int]] = set()
    excluded = {
        "require", "assert", "revert", "if", "while", "for", "return", "emit",
        "keccak256", "abi", "address", "bytes", "uint", "int", "string", "bool",
        "unchecked", "delete",
    }

    def declaration_key(item: FunctionModel) -> tuple[str, str, int]:
        return (item.name, item.source or contract.source, item.line)

    def walk(item: FunctionModel, depth: int) -> None:
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        key = declaration_key(item)
        if key in visited:
            return
        visited.add(key)
        source = item.source or contract.source
        if item.body_scope == "out_of_scope":
            blockers.append(f"blocked:callee_body_out_of_scope:{source}::{item.name}")
            return
        body = _function_body(item, contract)
        if body is None:
            blockers.append(f"blocked:source_body_unavailable:{source}::{item.name}")
            return

        writes = tuple(item.writes) or tuple(
            name for name in contract.state_variables
            if re.search(
                r"\\b" + re.escape(name) +
                r"\\b(?:\\s*\\[[^]]*\\])*\\s*(?:=(?!=)|\\+=|-=|\\*=|/=|\\+\\+|--)",
                body,
            )
        )
        for name in writes:
            record = f"write:{name}"
            if record not in effects:
                effects.append(record)
            provenance.append(f"effect_provenance:{record}:{source}:{item.line}:{item.name}")

        # Low-level calls are only attributed when the target is explicitly
        # recognizable. delegatecall is never assigned callee storage effects.
        if re.search(r"\\.delegatecall\\s*\\(", body):
            blockers.append(f"blocked:delegatecall_storage_context_unmodeled:{source}:{item.line}:{item.name}")
        for low in re.finditer(r"\\b([A-Za-z_]\\w*)\\s*\\.\\s*call\\s*(?:\\{|\\()", body):
            receiver = low.group(1)
            if receiver.lower() in {"permit2", "allowanceholder"}:
                record = f"external_call:{receiver}"
                if record not in effects:
                    effects.append(record)
                provenance.append(f"effect_provenance:{record}:{source}:{item.line}:{item.name}")
            else:
                blockers.append(f"blocked:low_level_call_target_unresolved:{receiver}:{source}:{item.line}:{item.name}")
        for low in re.finditer(r"\\.staticcall\\s*\\(", body):
            # staticcall cannot write target storage, but can affect branch decisions;
            # classify only as an external read boundary and do not follow it.
            effects.append(f"external_staticcall:{source}:{item.line}")
            provenance.append(f"effect_provenance:external_staticcall:{source}:{item.line}:{item.name}")

        # Calls to signature authorization are a deliberate model boundary.
        if re.search(r"(?<![.\\w])_dispatchPermit\\s*\\(", body):
            blockers.append("blocked:signature_authorization_unsupported")
        calls: list[str] = []
        for match in re.finditer(r"(?<![.\\w])([A-Za-z_]\\w*)\\s*\\(", body):
            name = match.group(1)
            if name in excluded or name == item.name or name.startswith("_dispatchPermit"):
                continue
            # Ignore calls whose receiver is explicit; they are handled as external boundaries.
            prefix = body[max(0, match.start() - 80):match.start()]
            if re.search(r"[.>]\\s*$", prefix):
                continue
            candidates = by_name.get(name, [])
            if not candidates:
                continue
            # Overloads require exact argument-type resolution, which this lexical
            # walker does not pretend to perform.
            if len(candidates) > 1:
                blockers.append(f"blocked:internal_overload_ambiguous:{name}:{source}:{item.line}")
                continue
            callee = candidates[0]
            if callee.body_scope == "out_of_scope":
                blockers.append(f"blocked:callee_body_out_of_scope:{callee.source or contract.source}::{name}")
                continue
            calls.append(name)
            walk(callee, depth + 1)

        # The model records external call facts separately from source call syntax.
        for call in item.external_calls:
            call_text = ".".join(str(part) for part in call) if isinstance(call, (tuple, list)) else str(call)
            lowered = call_text.lower()
            if "permit2" in lowered or "allowanceholder" in lowered:
                target = "Permit2" if "permit2" in lowered else "AllowanceHolder"
                record = f"external_call:{target}"
                if record not in effects:
                    effects.append(record)
                provenance.append(f"effect_provenance:{record}:{source}:{item.line}:{item.name}")

    if function.body_scope == "out_of_scope":
        return (), (), f"blocked:callee_body_out_of_scope:{function.source or contract.source}::{function.name}", 0
    walk(function, 0)
    # Calls in the observed Settler path form a small, acyclic internal graph;
    # the maximum observed simple-path depth is the budget. A cycle is handled
    # by visited-signature protection rather than an arbitrary global cutoff.
    budget = max_depth
    blocker = next((item for item in blockers if item == "blocked:signature_authorization_unsupported"), None)
    if blocker is None and blockers:
        blocker = blockers[0]
    if not blocker:
        effects.insert(0, "resolved_effects" if any(item.startswith("write:") for item in effects) else "resolved_read")
    provenance.extend(f"callee_walk_depth:{budget}" for _ in (0,) if budget)
    return tuple(dict.fromkeys(effects)), tuple(dict.fromkeys(provenance)), blocker, budget


def _unresolved_execution_path(
    contract: ContractModel, function: FunctionModel
) -> tuple[str, ...]:
    """Compatibility surface: return blocker/effect provenance from bounded walk."""
    effects, provenance, blocker, _depth = _bounded_callee_walk(contract, function)
    if blocker:
        return (blocker, *provenance)
    return (*effects, *provenance)

def _effective_functions(contract: ContractModel) -> tuple[FunctionModel, ...]:
    """Return one model per effective signature, preferring the nearest declaration.

    Direct declarations precede inherited declarations; inherited models are
    ordered from nearer to more distant ancestors by the Solidity model. The
    first declaration for a signature wins and retains its source provenance.
    """
    effective: list[FunctionModel] = []
    seen_signatures: set[tuple[str, tuple[str, ...]]] = set()
    for function in (*contract.functions, *contract.inherited_functions):
        signature = (
            function.name,
            tuple(parameter.type.strip() for parameter in function.parameters),
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        effective.append(function)
    return tuple(effective)


def generate_hypothesis_seeds(contracts: tuple[ContractModel, ...] | list[ContractModel]) -> tuple[HypothesisSeed, ...]:
    """Emit provisional questions from writes or unresolved execution paths."""
    seeds: list[HypothesisSeed] = []
    for contract in contracts:
        for function in _effective_functions(contract):
            if function.visibility not in {"public", "external"}:
                continue
            observed_writes = _observed_writes(contract, function)
            lifecycle = _is_lifecycle_surface(function)
            unresolved = _unresolved_execution_path(contract, function)
            if not observed_writes and not lifecycle and not unresolved:
                continue

            source = function.source or contract.source
            if lifecycle:
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
                seed_id=f"SEED-AUTH-{contract.name}-{function.name}-{function.line}",
                target_contract=contract.name,
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
