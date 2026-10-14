from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import subprocess
import tempfile
import re
import shutil
import tomllib

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.compiler_state import compile_state_effects
from cydra.foundry import ExecutionResult, require_executed, run_foundry_test, test_path_for
from cydra.authorization_pipeline import investigate_authorization
from cydra.experiment_planning import bind_experiment
from cydra.reasoning import (
    _declared_modifiers,
    _effective_declared_modifiers,
    initialization_surface_functions,
    plan_access_control_experiment,
)

_IMPORT_RE = re.compile(r'''\bimport\s+(?:[^\"']+\s+from\s+)?[\"']([^\"']+)[\"']\s*;''')

def _seed_coverage_allows_measurement(hypotheses, seeds) -> bool:
    """Seed coverage is a successful measurement, never finding readiness."""
    return not hypotheses and bool(seeds)



def _staged_source_import(
    execution_project: Path,
    source_relative: Path,
    test_parent: Path,
) -> str:
    """Build an import relative to the staged project, not the original checkout root."""
    return os.path.relpath(
        execution_project / source_relative, test_parent
    ).replace(os.sep, "/")


def _resolve_hypothesis_contract(result, hypothesis):
    """Resolve a candidate only by its full source identity tuple; never fall back to name."""
    if not all((
        hypothesis.source_path,
        hypothesis.declaring_contract,
        hypothesis.source_line is not None,
    )):
        raise SystemExit(
            f"candidate-missing: incomplete identity tuple for {hypothesis.hypothesis_id}"
        )

    identity = (
        str(Path(hypothesis.source_path).resolve()),
        hypothesis.declaring_contract,
        hypothesis.target_function,
        hypothesis.source_line,
    )

    matches = [
        contract
        for contract in result.contracts
        if contract.name == identity[1]
        and str(Path(contract.source).resolve()) == identity[0]
        and sum(
            1
            for function in contract.functions
            if function.name == identity[2]
            and function.line == identity[3]
            and str(Path(function.source or contract.source).resolve()) == identity[0]
        ) == 1
    ]

    if not matches:
        raise SystemExit(
            f"candidate-missing: no contract/function matches {identity!r}"
        )

    if len(matches) != 1:
        raise SystemExit(
            f"candidate-ambiguous: {len(matches)} contracts match {identity!r}"
        )

    return matches[0]


def _parse_candidate_identity(value: str) -> tuple[str, str, str, int]:
    """Parse source-path::contract::function::line without name-only fallbacks."""
    parts = value.split("::")
    if len(parts) != 4 or not all(part.strip() for part in parts):
        raise ValueError(
            "requested candidate must be SOURCE_PATH::CONTRACT::FUNCTION::LINE"
        )
    source_path, contract, function, raw_line = (part.strip() for part in parts)
    try:
        line = int(raw_line)
    except ValueError as exc:
        raise ValueError("requested candidate source line must be a positive integer") from exc
    if line < 1:
        raise ValueError("requested candidate source line must be a positive integer")
    return source_path.replace("\\", "/"), contract, function, line


def _select_hypotheses(
    hypotheses,
    requested_candidate: str | None,
    *,
    target_path: str,
):
    """Return all blind candidates or one identity matched within the pinned source path."""
    if requested_candidate is None:
        return tuple(hypotheses)

    requested_path, requested_contract, requested_function, requested_line = (
        _parse_candidate_identity(requested_candidate)
    )
    normalized_target = target_path.replace("\\", "/").strip("/")
    requested_path = requested_path.strip("/")
    # The short Vault.sol spelling is safe only because the campaign separately
    # pins target_path. It is not a global basename search across the model.
    if "/" not in requested_path:
        if Path(normalized_target).name != requested_path:
            normalized_target = "__candidate_path_mismatch__"
        requested_path = normalized_target

    def path_matches(candidate_path: str | None) -> bool:
        if not candidate_path:
            return False
        normalized = str(candidate_path).replace("\\", "/").strip("/")
        requested = requested_path.rstrip("/")
        return normalized == requested or normalized.endswith("/" + requested)

    matches = [
        item for item in hypotheses
        if path_matches(item.source_path)
        and item.declaring_contract == requested_contract
        and item.target_function == requested_function
        and item.source_line == requested_line
    ]
    if not matches:
        raise SystemExit(
            "candidate-missing: no hypothesis matches requested identity "
            f"{requested_candidate!r}"
        )
    if len(matches) != 1:
        raise SystemExit(
            "candidate-ambiguous: "
            f"{len(matches)} hypotheses match requested identity {requested_candidate!r}"
        )
    return (matches[0],)


def _campaign_collection_payload(
    *,
    target: str,
    campaign_mode: str,
    requested_candidate: str | None,
    hypotheses,
    candidate_results,
    seeds=(),
    outcome_records=(),
):
    """Serialize every candidate result; targeted mode alone has a final_result."""
    results = list(candidate_results)
    final_result = results[0] if campaign_mode == "targeted" and len(results) == 1 else None
    return {
        "target": target,
        "campaign_mode": campaign_mode,
        "requested_candidate": requested_candidate,
        "candidate_count": len(hypotheses),
        "candidate_order": [item.hypothesis_id for item in hypotheses],
        "hypothesis_seeds": _json(seeds),
        "non_transitions": [
            item for item in outcome_records if item.get("outcome") == "non_transition"
        ],
        "seed_outcomes": _json(outcome_records),
        "candidate_results": results,
        "final_result": final_result,
        "classification": final_result.get("classification") if final_result else "COLLECTION",
        "finding_gate": final_result.get("finding_gate", "NOT_READY") if final_result else "NOT_READY",
    }


def _write_campaign_collection(output: Path | None, payload: dict) -> None:
    """Persist the growing collection after each candidate so later failures lose no evidence."""
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_json(payload), indent=2) + "\n", encoding="utf-8")


def _prepare_isolated_foundry_project(target_root: Path, source: Path, destination: Path) -> Path:
    """Stage the import closure without relocating files relative to the selected project root."""
    src_root = destination
    test_root = destination / "test" / "generated"
    test_root.mkdir(parents=True, exist_ok=True)

    pending = [source]
    copied: set[Path] = set()
    unresolved: list[dict[str, str]] = []
    remappings: list[tuple[str, str]] = []
    remappings_file = target_root / "remappings.txt"
    if remappings_file.exists():
        for raw_line in remappings_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            prefix, destination_path = line.split("=", 1)
            if prefix and destination_path:
                remappings.append((prefix, destination_path))

    foundry_config = target_root / "foundry.toml"
    if foundry_config.exists():
        try:
            config = tomllib.loads(foundry_config.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(f"staging_unsupported: invalid foundry.toml: {exc}") from exc
        profile_default = config.get("profile", {}).get("default", {})
        configured_remappings = profile_default.get("remappings", config.get("remappings", []))
        if not isinstance(configured_remappings, list) or not all(
            isinstance(item, str) for item in configured_remappings
        ):
            raise RuntimeError("staging_unsupported: foundry remappings must be an array of strings")
        for candidate in configured_remappings:
            if "=" not in candidate:
                raise RuntimeError(f"staging_unsupported: invalid foundry remapping: {candidate!r}")
            prefix, destination_path = candidate.split("=", 1)
            if prefix and destination_path:
                remappings.append((prefix, destination_path))
    remappings = list(dict.fromkeys(remappings))

    while pending:
        current = pending.pop().resolve()
        if current in copied:
            continue
        try:
            relative = current.relative_to(target_root.resolve())
        except ValueError:
            unresolved.append({
                "importer": str(current),
                "import": "",
                "reason": "dependency_resolved_outside_selected_project_root",
            })
            continue
        copied.add(current)
        destination_file = src_root / relative
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, destination_file)

        text = current.read_text(encoding="utf-8")
        for imported in _IMPORT_RE.findall(text):
            dependency = None
            if imported.startswith("."):
                dependency = (current.parent / imported).resolve()
            elif imported.startswith(("contracts/", "lib/", "node_modules/")):
                dependency = (target_root / imported).resolve()
            else:
                for prefix, destination_path in sorted(remappings, key=lambda item: len(item[0]), reverse=True):
                    if imported.startswith(prefix):
                        suffix = imported[len(prefix):]
                        dependency = (target_root / destination_path / suffix).resolve()
                        break
                if dependency is None:
                    # Package imports may be resolvable directly from node_modules.
                    dependency = (target_root / "node_modules" / imported).resolve()
            if dependency.is_file():
                if dependency not in copied:
                    pending.append(dependency)
            else:
                unresolved.append({
                    "importer": str(current.relative_to(target_root.resolve())),
                    "import": imported,
                    "expected_path": str(dependency.relative_to(target_root.resolve())) if dependency.is_relative_to(target_root.resolve()) else str(dependency),
                    "reason": "import_not_found_in_pinned_project",
                })

    if unresolved:
        detail = json.dumps(unresolved, sort_keys=True)
        raise RuntimeError("staging_unsupported: unresolved import closure: " + detail)

    remapping_lines = []
    for prefix, destination_path in remappings:
        # The selected project's relative directory structure is preserved verbatim.
        remapping_lines.append(f"{prefix}={destination_path}")
    remapping_literal = ", ".join(repr(item) for item in remapping_lines)
    (destination / "foundry.toml").write_text(
        '[profile.default]\n'
        'src = "."\n'
        'test = "test"\n'
        'libs = ["lib"]\n'
        'auto_detect_solc = true\n'
        f"remappings = [{remapping_literal}]\n",
        encoding="utf-8",
    )
    hardhat_console = destination / "lib" / "hardhat" / "console.sol"
    hardhat_console.parent.mkdir(parents=True, exist_ok=True)
    hardhat_console.write_text("pragma solidity ^0.6.12; library console {}\n", encoding="utf-8")
    (destination / "remappings.txt").write_text(
        "\n".join(remapping_lines) + ("\n" if remapping_lines else ""),
        encoding="utf-8",
    )
    return test_root


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=cwd, text=True, capture_output=True, check=True
    ).stdout.strip()


def _observed_bool(output: str, field: str) -> bool | None:
    match = re.search(rf"^\s*{re.escape(field)}\s+(true|false)\s*$", output, re.MULTILINE | re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).lower() == "true"


def _auth_modifier(source):
    """Choose an owner/admin guard for the causal patch, never a merely frequent role guard."""
    defs = {}
    for match in re.finditer(r"\bmodifier\s+(\w+)\s*(?:\(([^)]*)\))?\s*\{", source):
        # The current patcher inserts a modifier without arguments. Parameterized
        # modifiers are therefore not safe controls and must be excluded.
        if (match.group(2) or "").strip():
            continue
        body = source[match.end():]
        depth = 1
        for index, char in enumerate(body):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    defs[match.group(1)] = body[:index]
                    break

    guarded = {}
    for match in re.finditer(r"\bfunction\s+\w+\s*\([^)]*\)([^{};]*)\{", source):
        for token in re.findall(r"\b[A-Za-z_]\w*\b", match.group(1)):
            body = defs.get(token)
            delegated_guard = bool(
                body
                and re.search(r"\b(?:_checkOwner|_checkRole|_checkAdmin|_checkGovernance|_authorize|_checkAccess)\s*\(", body)
            )
            direct_guard = bool(
                body
                and re.search(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b", body)
                and re.search(r"\b(?:require|revert|assert)\b", body)
            )
            if direct_guard or delegated_guard:
                guarded[token] = body

    # A popular role-specific guard such as onlyRouter is not an acceptable
    # patch for an administrative setter: it can permanently brick configuration.
    preferred = []
    for name, body in guarded.items():
        lowered = name.lower()
        owner_named = "owner" in lowered
        admin_named = any(part in lowered for part in ("admin", "governance", "governor", "onlygov"))
        owner_predicate = bool(re.search(r"\bowner\s*\(\)", body))
        admin_predicate = bool(re.search(r"\b(?:DEFAULT_ADMIN_ROLE|ADMIN_ROLE|GOVERNANCE_ROLE)\b", body))
        if owner_named or admin_named or owner_predicate or admin_predicate:
            rank = (
                100 if owner_named or owner_predicate
                else 90 if "admin" in lowered or admin_predicate
                else 80
            )
            preferred.append((rank, name))

    if not preferred:
        return None
    highest = max(rank for rank, _ in preferred)
    winners = sorted(name for rank, name in preferred if rank == highest)
    return winners[0] if len(winners) == 1 else None

def _apply_auth_control(source, function_name, modifier):
    original=source.read_text(encoding="utf-8")
    pat=re.compile(rf"(\bfunction\s+{re.escape(function_name)}\s*\([^)]*\))([^{{;]*)(\{{)",re.MULTILINE)
    m=pat.search(original)
    if not m: raise RuntimeError(f"cannot patch {function_name}")
    tail=m.group(2)
    if re.search(rf"\b{re.escape(modifier)}\b",tail): raise RuntimeError("target already has inferred modifier")
    source.write_text(original[:m.start(2)]+tail+" "+modifier+" "+original[m.end(2):],encoding="utf-8")
    return original

def _patched_auth_test(generated,destination):
    s=generated.read_text(encoding="utf-8")
    patched, count = re.subn(
        r'require\(ok,\s*"[^"]*"\);',
        "if (!ok) return;",
        s,
        count=1,
    )
    if count == 0:
        patched, count = re.subn(
            r'require\(\s*!ok,\s*"[^"]*"\s*\);',
            "if (!ok) return;",
            s,
            count=1,
        )
    if count != 1:
        raise RuntimeError("authorization assertion marker missing")
    destination.write_text(patched,encoding="utf-8")

def _json(v):
    if hasattr(v,"__dict__"): return {k:_json(x) for k,x in v.__dict__.items()}
    if isinstance(v,(tuple,list)): return [_json(x) for x in v]
    if isinstance(v,dict): return {str(k):_json(x) for k,x in v.items()}
    return v


def _no_hypothesis_payload(target, compiler, result, related_intent_parity_hypotheses=()):
    """Preserve no-auth and unsupported-related-hypothesis outcomes without calling either a finding."""
    related = _json(related_intent_parity_hypotheses)
    has_related = bool(related_intent_parity_hypotheses)
    lifecycle_surfaces = [
        {
            "contract": contract.name,
            "function": function.name,
            "source": function.source or contract.source,
            "source_line": function.line,
            "modifiers": list(function.modifiers),
            "writes": list(function.writes),
            "disposition": "DEPLOYMENT_STATE_REQUIRED",
            "reason": (
                "Initialization modifiers and naming identify a lifecycle-sensitive surface; "
                "do not promote it to a vulnerability without evidence of the deployed proxy's "
                "initialization state and deployment calldata."
            ),
        }
        for contract in result.contracts
        for function in initialization_surface_functions(contract)
    ]
    surface_coverage = []
    for contract in result.contracts:
        for function in contract.functions:
            if function.visibility not in {"public", "external"}:
                continue
            declared_modifiers = list(_declared_modifiers(contract, function))
            effective_modifiers = list(_effective_declared_modifiers(contract, function))
            inherited_modifiers = [item for item in effective_modifiers if item not in declared_modifiers]
            modifier_provenance = (
                "inherited_super_dispatch" if inherited_modifiers
                else "declared" if declared_modifiers
                else "none"
            )
            modifiers = effective_modifiers
            writes = list(function.writes)
            if modifiers:
                disposition = "MODIFIER_PRESENT_REQUIRES_SEMANTIC_VALIDATION"
            elif function.name.startswith(("set", "add", "remove", "update", "accept")) and writes:
                disposition = "ADMIN_NAMED_UNGUARDED_CANDIDATE"
            else:
                disposition = "NOT_SELECTED_BY_ADMIN_NAME_WRITE_HEURISTIC"
            surface_coverage.append({
                "contract": contract.name,
                "source": contract.source,
                "function": function.name,
                "visibility": function.visibility,
                "modifiers": modifiers,
                "declared_modifiers": declared_modifiers,
                "effective_modifiers": effective_modifiers,
                "modifier_provenance": modifier_provenance,
                "model_writes": writes,
                "heuristic_disposition": disposition,
                "is_finding": False,
            })
    return {
        "target": target,
        "compiler": {
            "executed": compiler.executed,
            "status": compiler.status,
            "versions": list(compiler.compiler_versions),
            "build_info_count": compiler.build_info_count,
            "matched_source_count": compiler.matched_source_count,
            "source_ast_found": compiler.source_ast_found,
            "source_dependency_count": compiler.source_dependency_count,
            "unresolved_imports": list(compiler.unresolved_imports),
            "semantic_relationship_count": len(compiler.evidence),
            "parameter_constraint_count": len(compiler.constraints),
        },
        "lifecycle_surfaces": lifecycle_surfaces,
        "contracts": [
            {
                "name": contract.name,
                "source": contract.source,
                "function_count": len(contract.functions),
                "functions": [
                    {
                        "name": function.name,
                        "visibility": function.visibility,
                        "modifiers": list(function.modifiers),
                        "effective_modifiers": list(_effective_declared_modifiers(contract, function)),
                        "modifier_provenance": (
                            "inherited_super_dispatch"
                            if set(_effective_declared_modifiers(contract, function)) - set(_declared_modifiers(contract, function))
                            else "declared" if _declared_modifiers(contract, function) else "none"
                        ),
                        "writes": list(function.writes),
                        "declaring_source": function.source or contract.source,
                    }
                    for function in contract.functions
                ],
            }
            for contract in result.contracts
        ],
        "surface_coverage": surface_coverage,
        "inherited_function_coverage": [
            {
                "contract": contract.name,
                "function": function.name,
                "visibility": function.visibility,
                "modifiers": list(function.modifiers),
                "writes": list(function.writes),
                "declaring_source": function.source or "unknown",
                "source_line": function.line,
                "is_finding": False,
            }
            for contract in result.contracts
            for function in contract.inherited_functions
            if function.visibility in {"public", "external"}
        ],
        "semantic_state_effects": [
            {
                "contract": item.contract,
                "function": item.function,
                "relation": item.relation,
                "target": item.target,
                "source": item.source,
                "source_location": item.source_location,
                "metadata": item.metadata,
            }
            for item in compiler.evidence
            if item.relation != "reference"
        ],
        "parameter_constraints": [
            {
                "contract": item.contract,
                "context": item.function,
                "context_kind": item.context_kind,
                "parameter": item.parameter,
                "parameter_index": item.parameter_index,
                "predicate": item.predicate,
                "kind": item.kind,
                "source": item.source,
                "source_location": item.source_location,
                "ast_node_id": item.ast_node_id,
            }
            for item in compiler.constraints
        ],
        "invariants": _json(result.invariants),
        "hypothesis_seeds": _json(getattr(result, "seeds", ())),
        "hypotheses": [],
        "related_intent_parity_hypotheses": related,
        "classification": "UNSUPPORTED_INTENT_PARITY_HYPOTHESIS" if has_related else "NO_AUTH_HYPOTHESIS",
        "disposition": "BLOCKED",
        "finding_gate": "NOT_READY",
        "blocker": "INTENT_PARITY_OUTSIDE_AUTH_SPECIALIST" if has_related else "NO_SUPPORTED_HYPOTHESIS",
        "note": (
            "Intent-parity hypotheses were generated, but this specialist only tests missing-authorization guards; preserve these candidates for a separate intent-parity campaign rather than treating them as missing-guard hypotheses. This is not a vulnerability finding."
            if has_related
            else "Absence of an authorization hypothesis is not evidence that the target is secure and is not a vulnerability finding."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind one-sided authorization backtest.")
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--target-path", required=True)
    parser.add_argument("--target-project", required=True)
    parser.add_argument(
        "--mode",
        choices=("blind", "targeted"),
        help="Campaign contract: blind measures all candidates; targeted measures one explicit identity.",
    )
    parser.add_argument(
        "--requested-candidate",
        help="Full identity SOURCE_PATH::CONTRACT::FUNCTION::LINE; implies targeted mode unless --mode blind is explicit.",
    )
    parser.add_argument("--expected-status", choices=("confirmed", "not_confirmed"), default="confirmed")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--measurement-only", action="store_true", help="Record measured outcomes without enforcing the benchmark expected-status exit code.")
    parser.add_argument("--allow-no-hypothesis", action="store_true", help="Record a no-hypothesis disposition as a completed measurement rather than failing the runner.")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--supplemental-file",
        action="append",
        default=[],
        help="Copy a target-relative file from another git ref using path@ref, for historical build repairs.",
    )
    parser.add_argument(
        "--target-npm-dependency",
        action="append",
        default=[],
        help="Install an npm package into the historical target before bounded execution.",
    )
    args = parser.parse_args()
    if args.mode == "blind" and args.requested_candidate is not None:
        parser.error("--requested-candidate is forbidden in blind mode")
    if args.mode == "targeted" and not args.requested_candidate:
        parser.error("--requested-candidate is required in targeted mode")
    campaign_mode = args.mode or (
        "targeted" if args.requested_candidate is not None else "blind"
    )
    if args.requested_candidate is not None:
        try:
            _parse_candidate_identity(args.requested_candidate)
        except ValueError as exc:
            parser.error(str(exc))

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="cydra-blind-auth-") as temp:
        checkout = Path(temp) / "target"
        subprocess.run(("git", "clone", "--no-tags", "--recurse-submodules", args.target_repo, str(checkout)), check=True)
        subprocess.run(("git", "-C", str(checkout), "fetch", "--no-tags", "origin", args.target_ref), check=True)
        subprocess.run(("git", "-C", str(checkout), "checkout", "--detach", args.target_ref), check=True)
        project = checkout / args.target_project
        source = checkout / args.target_path
        for supplemental in args.supplemental_file:
            try:
                relative_path, supplemental_ref = supplemental.rsplit("@", 1)
            except ValueError as exc:
                raise SystemExit(f"Invalid supplemental file {supplemental!r}; expected path@ref") from exc
            blob = subprocess.run(
                ("git", "-C", str(checkout), "show", f"{supplemental_ref}:{relative_path}"),
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            destination = checkout / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(blob, encoding="utf-8")
        compiler = compile_state_effects(project, source)
        result = investigate_authorization(
            source,
            target=f"{args.target_repo}@{args.target_ref}",
            semantic_evidence=compiler.evidence,
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-AUTH-001"]
        if args.requested_candidate is not None and not hypotheses:
            raise SystemExit(
                "candidate-missing: authorization derivation produced no candidates "
                "for the requested identity"
            )
        if args.requested_candidate is not None:
            hypotheses = list(
                _select_hypotheses(
                    hypotheses, args.requested_candidate, target_path=args.target_path
                )
            )
        related_intent_parity_hypotheses = [
            h for h in result.hypotheses
            if h.invariant_id.startswith("INV-INTENT-PARITY-")
        ]
        if not hypotheses:
            print("NO_AUTH_HYPOTHESIS")
            for contract in result.contracts:
                print("CONTRACT", contract.name, "functions=", len(contract.functions))
                for function in contract.functions:
                    print("FUNCTION", function.name, "visibility=", function.visibility, "modifiers=", function.modifiers, "writes=", function.writes)
            print("INVARIANTS", [item.__dict__ for item in result.invariants])
            payload = _no_hypothesis_payload(
                f"{args.target_repo}@{args.target_ref}:{args.target_path}",
                compiler,
                result,
                related_intent_parity_hypotheses=related_intent_parity_hypotheses,
            )
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(_json(payload), indent=2) + "\n", encoding="utf-8")
            print("DISPOSITION", payload["disposition"], "finding_gate=", payload["finding_gate"])
            if _seed_coverage_allows_measurement(hypotheses, result.seeds):
                payload["measurement_status"] = "SEEDS_READY_NO_AUTH_HYPOTHESIS"
                payload["seed_count"] = len(result.seeds)
                payload["finding_gate"] = "NOT_READY"
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(_json(payload), indent=2) + "\n", encoding="utf-8")
                print("SEED_COVERAGE", len(result.seeds), "measurement=PASS", "finding_gate=NOT_READY")
                return 0
            if args.allow_no_hypothesis:
                return 0
            raise SystemExit("blind authorization backtest produced no authorization hypothesis or measurable seed coverage")

        for dependency in args.target_npm_dependency:
            subprocess.run(
                ("npm", "install", dependency, "--no-save", "--ignore-scripts", "--no-audit", "--no-fund"),
                cwd=project,
                check=True,
            )

        execution_project = Path(temp) / "execution-project"
        try:
            _prepare_isolated_foundry_project(project, source, execution_project)
        except RuntimeError as exc:
            if not str(exc).startswith("staging_unsupported:"):
                raise
            payload = {
                "target": f"{args.target_repo}@{args.target_ref}:{args.target_path}",
                "classification": "STAGING_UNSUPPORTED",
                "disposition": "BLOCKED",
                "finding_gate": "NOT_READY",
                "staging_diagnostic": str(exc),
                "hypothesis_seeds": _json(getattr(result, "seeds", ())),
                "hypothesis": _json(hypotheses[0]) if hypotheses else None,
            }
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(_json(payload), indent=2) + "\n", encoding="utf-8")
            print("STAGING_UNSUPPORTED", str(exc))
            return 2
        for dependency in args.target_npm_dependency:
            package_name = dependency.split("@", 1)[0] if not dependency.startswith("@") else dependency.rsplit("@", 1)[0]
            if package_name in {"@openzeppelin/contracts", "@openzeppelin/contracts-upgradeable"}:
                package_leaf = package_name.split("/", 1)[1]
                package_source = project / "node_modules" / "@openzeppelin" / package_leaf
                package_destination = execution_project / "node_modules" / "@openzeppelin" / package_leaf
                package_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(package_source, package_destination, dirs_exist_ok=True)
                # Foundry does not search npm's node_modules tree by default.
                # Historical Alchemix imports use the package prefix directly,
                # so add the deterministic remapping in the isolated project.
                foundry_toml = execution_project / "foundry.toml"
                remapping = "@openzeppelin/=node_modules/@openzeppelin/"
                current = foundry_toml.read_text(encoding="utf-8")
                current = current.replace(
                    'remappings = [',
                    'remappings = [' + repr(remapping) + ', ',
                    1,
                )
                foundry_toml.write_text(current, encoding="utf-8")

        source_relative = Path(source).relative_to(project)
        candidate_results = []
        benchmark_mismatch = False
        readiness_failure = False
        target_label = f"{args.target_repo}@{args.target_ref}:{args.target_path}"

        def persist_collection():
            payload = _campaign_collection_payload(
                target=target_label,
                campaign_mode=campaign_mode,
                requested_candidate=args.requested_candidate,
                hypotheses=hypotheses,
                candidate_results=candidate_results,
                seeds=getattr(result, "seeds", ()),
                outcome_records=getattr(result, "outcome_records", ()),
            )
            _write_campaign_collection(args.output, payload)

        for hypothesis in hypotheses:
            experiment_matches = [
                item for item in result.experiments
                if item.hypothesis_id == hypothesis.hypothesis_id
            ]
            if len(experiment_matches) != 1:
                raise SystemExit(
                    "candidate-missing: expected exactly one experiment for "
                    f"{hypothesis.hypothesis_id}, got {len(experiment_matches)}"
                )
            planned_experiment = experiment_matches[0]
            experiment = bind_experiment(
                hypothesis,
                planned_experiment,
                target_function=hypothesis.target_function,
                planned_inputs=planned_experiment.planned_inputs,
            )
            contract = _resolve_hypothesis_contract(result, hypothesis)
            output = test_path_for(
                execution_project, f"generated/{hypothesis.hypothesis_id}.t.sol"
            )
            try:
                generated = generate_blind_authorization_test_from_experiment(
                    hypothesis,
                    experiment,
                    _staged_source_import(execution_project, source_relative, output.parent),
                    contract.name,
                    output,
                    contract,
                )
            except ValueError as exc:
                execution = ExecutionResult(
                    experiment_id=experiment.experiment_id,
                    target=str(source),
                    command=("cydra", "render_authorization_test"),
                    exit_code=2,
                    executed=False,
                    tests_run=0,
                    tests_failed=0,
                    status="UNMEASURABLE",
                    stdout="",
                    stderr=f"authorization experiment could not be rendered faithfully: {exc}",
                )
                outcome = classify_authorization_blind_execution(hypothesis, execution)
                candidate_payload = {
                    "candidate_identity": {
                        "source_path": hypothesis.source_path,
                        "declaring_contract": hypothesis.declaring_contract,
                        "target_function": hypothesis.target_function,
                        "source_line": hypothesis.source_line,
                    },
                    "hypothesis": _json(hypothesis),
                    "experiment": _json(experiment),
                    "contract": contract.name,
                    "blind_execution": _json(execution),
                    "classification": outcome.benchmark_status,
                    "verdict": outcome.verdict,
                    "verdict_reason": outcome.verdict_reason,
                    "finding_gate": "NOT_READY",
                }
                candidate_results.append(candidate_payload)
                if not args.measurement_only and outcome.benchmark_status != args.expected_status:
                    benchmark_mismatch = True
                persist_collection()
                print(
                    f"{hypothesis.hypothesis_id}: status={execution.status} "
                    f"classification={outcome.benchmark_status} "
                    f"evidence={outcome.evidence.evidence_id}"
                )
                continue

            execution = run_foundry_test(
                execution_project, generated, experiment.experiment_id, "blind"
            )
            print(
                "EXECUTION_STATUS", execution.status,
                "exit=", execution.exit_code,
                "tests=", execution.tests_run,
                "failed=", execution.tests_failed,
            )
            print(execution.stdout)
            print(execution.stderr)
            outcome = classify_authorization_blind_execution(hypothesis, execution)
            print(
                f"{hypothesis.hypothesis_id}: status={execution.status} "
                f"classification={outcome.benchmark_status} "
                f"evidence={outcome.evidence.evidence_id}"
            )
            candidate_payload = {
                "candidate_identity": {
                    "source_path": hypothesis.source_path,
                    "declaring_contract": hypothesis.declaring_contract,
                    "target_function": hypothesis.target_function,
                    "source_line": hypothesis.source_line,
                },
                "hypothesis": _json(hypothesis),
                "experiment": _json(experiment),
                "contract": contract.name,
                "blind_execution": _json(execution),
                "classification": outcome.benchmark_status,
                "verdict": outcome.verdict,
                "verdict_reason": outcome.verdict_reason,
                "finding_gate": "CONFIRMED_ONLY" if outcome.benchmark_status == "confirmed" else "NOT_READY",
            }

            if args.require_ready and outcome.benchmark_status == "confirmed":
                isolated_source = execution_project / source_relative
                # Causal-control discovery must include inherited modifiers in
                # imported dependencies, not only first-party files under src/.
                auth_sources = []
                for source_root_name in ("src", "lib"):
                    source_root = execution_project / source_root_name
                    if source_root.is_dir():
                        auth_sources.extend(source_root.rglob("*.sol"))
                auth_context = "\n".join(
                    path.read_text(encoding="utf-8")
                    for path in sorted(set(auth_sources))
                    if path.is_file()
                )
                modifier = _auth_modifier(auth_context)
                print("AUTHORIZATION_CONTROL", modifier)
                if modifier is None:
                    print("AUTHORIZATION_CAUSAL_CONTROL_UNAVAILABLE")
                    candidate_payload["finding_gate"] = "NOT_READY"
                    candidate_payload["causal_verification"] = {
                        "state": "not_verified",
                        "reason": "authorization causal control unavailable",
                    }
                    readiness_failure = True
                else:
                    original = _apply_auth_control(
                        isolated_source, hypothesis.target_function, modifier
                    )
                    try:
                        patched_test = generated.with_name(generated.stem + "-patched.t.sol")
                        shutil.copy2(generated, patched_test)
                        patched = run_foundry_test(
                            execution_project, patched_test,
                            hypothesis.hypothesis_id + ":patched", "patched",
                        )
                    finally:
                        isolated_source.write_text(original, encoding="utf-8")
                    causal = (
                        _observed_bool(execution.stdout, "CYDRA_OBS_CALL_SUCCEEDED") is True
                        and _observed_bool(execution.stdout, "CYDRA_OBS_STATE_CHANGED") is True
                        and _observed_bool(patched.stdout, "CYDRA_OBS_CALL_SUCCEEDED") is False
                        and _observed_bool(patched.stdout, "CYDRA_OBS_STATE_CHANGED") is False
                    )
                    reproduction = run_foundry_test(
                        execution_project, generated,
                        hypothesis.hypothesis_id + ":reproduction", "reproduction",
                    )
                    original = _apply_auth_control(
                        isolated_source, hypothesis.target_function, modifier
                    )
                    try:
                        repro_test = generated.with_name(
                            generated.stem + "-reproduction-patched.t.sol"
                        )
                        shutil.copy2(generated, repro_test)
                        repro_patched = run_foundry_test(
                            execution_project, repro_test,
                            hypothesis.hypothesis_id + ":reproduction-patched",
                            "reproduction-patched",
                        )
                    finally:
                        isolated_source.write_text(original, encoding="utf-8")
                    repro = (
                        _observed_bool(reproduction.stdout, "CYDRA_OBS_CALL_SUCCEEDED") is True
                        and _observed_bool(reproduction.stdout, "CYDRA_OBS_STATE_CHANGED") is True
                        and _observed_bool(repro_patched.stdout, "CYDRA_OBS_CALL_SUCCEEDED") is False
                        and _observed_bool(repro_patched.stdout, "CYDRA_OBS_STATE_CHANGED") is False
                    )
                    print("PATCHED_EXECUTION_STATUS", patched.status)
                    print("PATCHED_RAW_OBSERVATIONS")
                    print(patched.stdout)
                    print("CAUSAL_VERIFICATION", causal)
                    print("REPRODUCTION_EXECUTION_STATUS", reproduction.status)
                    print("REPRODUCTION_PATCHED_EXECUTION_STATUS", repro_patched.status)
                    print("REPRODUCTION_PATCHED_RAW_OBSERVATIONS")
                    print(repro_patched.stdout)
                    print("REPRODUCTION_VERIFICATION", repro)
                    candidate_payload.update({
                        "authorization_control": modifier,
                        "patched_execution": _json(patched),
                        "causal_verification": {
                            "state": "verified" if causal else "not_verified",
                            "chain_id": "causal:authorization-modifier-differential",
                        },
                        "reproduction_execution": _json(reproduction),
                        "reproduction_patched_execution": _json(repro_patched),
                        "reproduction_verification": {
                            "state": "verified" if repro else "not_verified",
                            "chain_id": "reproduction:authorization-modifier-differential",
                        },
                        "finding_gate": (
                            "READY"
                            if causal and repro
                            and compiler.status != "source_dependency_closure_incomplete"
                            else "NOT_READY"
                        ),
                    })
                    if not (causal and repro):
                        readiness_failure = True

            candidate_results.append(candidate_payload)
            if not args.measurement_only and outcome.benchmark_status != args.expected_status:
                benchmark_mismatch = True
            # Persist incrementally: a later candidate failure must not erase earlier evidence.
            persist_collection()

        final_payload = _campaign_collection_payload(
            target=target_label,
            campaign_mode=campaign_mode,
            requested_candidate=args.requested_candidate,
            hypotheses=hypotheses,
            candidate_results=candidate_results,
            seeds=getattr(result, "seeds", ()),
            outcome_records=getattr(result, "outcome_records", ()),
        )
        _write_campaign_collection(args.output, final_payload)
        if readiness_failure:
            return 4
        if benchmark_mismatch:
            return 2
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
