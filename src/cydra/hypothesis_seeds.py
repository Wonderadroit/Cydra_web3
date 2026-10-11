from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Literal

from .models import ContractModel, FunctionModel

SeedStatus = Literal["seed", "testable", "blocked"]


@dataclass(frozen=True)
class HypothesisSeed:
    """A provisional, provenance-linked security question, not a finding."""
    seed_id: str
    target_contract: str
    target_function: str
    question: str
    invariant: str
    falsification: str
    preconditions_needed: tuple[str, ...]
    status: SeedStatus
    source: str
    source_line: int
    observed_writes: tuple[str, ...]
    uncertainty: tuple[str, ...]


def _is_lifecycle_surface(function: FunctionModel) -> bool:
    name = function.name.lower()
    modifiers = {item.lower() for item in function.modifiers}
    return (
        name.startswith(("initialize", "initialise", "init", "reinitialize", "reinitialise"))
        or "initializer" in modifiers
        or any(item.startswith("reinitializer") for item in modifiers)
    )


def _observed_writes(contract: ContractModel, function: FunctionModel) -> tuple[str, ...]:
    if function.writes:
        return tuple(function.writes)
    # Recover a narrow source-linked witness when the first-pass model omitted it.
    try:
        source = Path(function.source or contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()
    pattern = re.compile(r"\bfunction\s+" + re.escape(function.name) + r"\s*\([^)]*\)[^{;]*\{", re.MULTILINE)
    match = pattern.search(source)
    if not match:
        return ()
    depth = 1
    end = match.end()
    while end < len(source) and depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    body = source[match.end():end - 1]
    writes = [
        name for name in contract.state_variables
        if re.search(r"\b" + re.escape(name) + r"\b(?:\s*\[[^]]*\])*\s*(?:=(?!=)|\+=|-=|\*=|/=|\+\+|--)", body)
    ]
    return tuple(sorted(set(writes)))


def generate_hypothesis_seeds(contracts: tuple[ContractModel, ...] | list[ContractModel]) -> tuple[HypothesisSeed, ...]:
    """Emit provisional questions from modeled externally callable state writes.

    This stage asks questions only. It neither tests the target nor declares a
    vulnerability. Unknown deployment details are retained as prerequisites.
    """
    seeds: list[HypothesisSeed] = []
    for contract in contracts:
        for function in contract.functions:
            if function.visibility not in {"public", "external"}:
                continue
            observed_writes = _observed_writes(contract, function)
            lifecycle = _is_lifecycle_surface(function)
            if not observed_writes and not lifecycle:
                continue
            writes = ", ".join(observed_writes) if observed_writes else "lifecycle-sensitive state"
            source = function.source or contract.source
            if lifecycle:
                question = f"Can a caller outside the intended trust boundary change {writes} through {function.name} in a reachable deployment state?"
                prerequisites = ("deployment_evidence", "initialization_state", "proxy_or_deployment_context")
                status: SeedStatus = "blocked"
                uncertainty = (
                    "deployment and proxy context are unknown from source modeling alone",
                    "initialization state is unknown",
                    "intended privileged actor must be established from target evidence",
                )
            else:
                question = f"Can a caller outside the intended trust boundary change {writes} through {function.name}?"
                prerequisites = ("deployment_or_local_fork", "intended_authorization_boundary", "control_actor_setup")
                status = "seed"
                uncertainty = (
                    "source-level writes do not establish runtime reachability",
                    "effective inherited/helper guards require validation",
                )
            seeds.append(HypothesisSeed(
                seed_id=f"SEED-AUTH-{contract.name}-{function.name}-{function.line}",
                target_contract=contract.name,
                target_function=function.name,
                question=question,
                invariant=f"Only an actor authorized by the evidenced trust boundary may change security-relevant state ({writes}).",
                falsification=f"Under documented preconditions, a caller outside that boundary changes {writes} through {function.name}; compare the state delta with a protected control.",
                preconditions_needed=prerequisites,
                status=status,
                source=source,
                source_line=function.line,
                observed_writes=observed_writes,
                uncertainty=uncertainty,
            ))
    return tuple(seeds)


def seeds_as_dicts(seeds: tuple[HypothesisSeed, ...]) -> list[dict[str, object]]:
    """Return stable JSON-ready records for campaign artifacts."""
    return [asdict(seed) for seed in seeds]
