from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import subprocess
import tempfile
import re
import shutil

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.compiler_state import compile_state_effects
from cydra.foundry import ExecutionResult, require_executed, run_foundry_test, test_path_for
from cydra.authorization_pipeline import investigate_authorization
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


def _materialize_target_dependencies(project: Path) -> dict:
    """Install manifest-declared npm dependencies without executing lifecycle scripts."""
    manifest = project / "package.json"
    if not manifest.is_file():
        return {
            "status": "NOT_REQUIRED",
            "package_manager": None,
            "lockfile": None,
            "confidence": "not_applicable",
            "lifecycle_scripts_disabled": True,
            "command": [],
            "detail": "No package.json in target project.",
        }

    try:
        package = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "BLOCKED",
            "package_manager": None,
            "lockfile": None,
            "confidence": "none",
            "lifecycle_scripts_disabled": True,
            "command": [],
            "detail": f"Could not parse package.json: {exc}",
        }

    dependency_sections = ("dependencies", "devDependencies", "optionalDependencies")
    if not any(package.get(section) for section in dependency_sections):
        return {
            "status": "NOT_REQUIRED",
            "package_manager": None,
            "lockfile": None,
            "confidence": "not_applicable",
            "lifecycle_scripts_disabled": True,
            "command": [],
            "detail": "package.json declares no installable dependency sections.",
        }

    lockfiles = [
        (name, manager)
        for name, manager in (
            ("package-lock.json", "npm"),
            ("pnpm-lock.yaml", "pnpm"),
            ("yarn.lock", "yarn"),
            ("bun.lock", "bun"),
            ("bun.lockb", "bun"),
        )
        if (project / name).is_file()
    ]
    distinct_managers = {manager for _, manager in lockfiles}
    if len(lockfiles) > 1:
        return {
            "status": "BLOCKED",
            "package_manager": None,
            "lockfile": [name for name, _ in lockfiles],
            "confidence": "none",
            "lifecycle_scripts_disabled": True,
            "command": [],
            "detail": "Multiple package-manager lockfiles are present; refusing to guess.",
        }

    if lockfiles:
        lockfile, manager = lockfiles[0]
        confidence = "lockfile_pinned"
    else:
        lockfile, manager = None, "npm"
        confidence = "manifest_unlocked_lower_confidence"

    if manager == "npm":
        executable = shutil.which("npm")
        prefix = [executable] if executable else []
        install_args = (
            ["ci", "--ignore-scripts", "--no-audit", "--no-fund"]
            if lockfile == "package-lock.json"
            else ["install", "--ignore-scripts", "--no-audit", "--no-fund"]
        )
    elif manager in {"pnpm", "yarn"}:
        executable = shutil.which(manager)
        if executable:
            prefix = [executable]
        elif shutil.which("corepack"):
            prefix = [shutil.which("corepack"), manager]
        else:
            prefix = []
        if manager == "pnpm":
            install_args = ["install", "--ignore-scripts", "--frozen-lockfile"]
        else:
            install_args = []
    else:
        executable = shutil.which("bun")
        prefix = [executable] if executable else []
        install_args = ["install", "--ignore-scripts", "--frozen-lockfile"]

    if not prefix:
        return {
            "status": "BLOCKED",
            "package_manager": manager,
            "lockfile": lockfile,
            "confidence": confidence,
            "lifecycle_scripts_disabled": True,
            "command": [],
            "detail": f"Required package manager {manager!r} is unavailable; no fallback was attempted.",
        }

    if manager == "yarn":
        try:
            version_probe = subprocess.run(
                prefix + ["--version"],
                cwd=project,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "status": "BLOCKED",
                "package_manager": manager,
                "lockfile": lockfile,
                "confidence": confidence,
                "lifecycle_scripts_disabled": True,
                "command": prefix + ["--version"],
                "detail": f"Could not query Yarn version safely: {exc}",
            }
        if version_probe.returncode != 0:
            return {
                "status": "BLOCKED",
                "package_manager": manager,
                "lockfile": lockfile,
                "confidence": confidence,
                "lifecycle_scripts_disabled": True,
                "command": prefix + ["install", "--ignore-scripts"],
                "detail": "Could not determine Yarn version to select lockfile-safe install flags.",
                "stderr": (version_probe.stderr or "")[-4000:],
            }
        version_match = re.match(r"\s*(\d+)", version_probe.stdout or "")
        if not version_match:
            return {
                "status": "BLOCKED",
                "package_manager": manager,
                "lockfile": lockfile,
                "confidence": confidence,
                "lifecycle_scripts_disabled": True,
                "command": prefix + ["install", "--ignore-scripts"],
                "detail": "Yarn version output was not parseable.",
            }
        if int(version_match.group(1)) == 1:
            install_args = ["install", "--ignore-scripts", "--frozen-lockfile", "--non-interactive"]
        else:
            install_args = ["install", "--ignore-scripts", "--immutable"]

    command = prefix + install_args
    if "--ignore-scripts" not in command:
        return {
            "status": "BLOCKED",
            "package_manager": manager,
            "lockfile": lockfile,
            "confidence": confidence,
            "lifecycle_scripts_disabled": False,
            "command": command,
            "detail": "Safety invariant violated: install command does not disable lifecycle scripts.",
        }

    try:
        completed = subprocess.run(
            command,
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
            timeout=900,
        )
        return {
            "status": "INSTALLED" if completed.returncode == 0 else "BLOCKED",
            "package_manager": manager,
            "lockfile": lockfile,
            "confidence": confidence,
            "lifecycle_scripts_disabled": True,
            "command": command,
            "return_code": completed.returncode,
            "stdout": (completed.stdout or "")[-4000:],
            "stderr": (completed.stderr or "")[-4000:],
            "detail": (
                "Dependencies installed with lifecycle scripts disabled."
                if completed.returncode == 0
                else "Package-manager installation failed; isolated execution must remain unmeasurable."
            ),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "BLOCKED",
            "package_manager": manager,
            "lockfile": lockfile,
            "confidence": confidence,
            "lifecycle_scripts_disabled": True,
            "command": command,
            "detail": f"Dependency installation could not complete: {exc}",
        }



def _prepare_isolated_foundry_project(target_root: Path, source: Path, destination: Path) -> Path:
    """Copy only the target's local Solidity import closure into a clean Foundry root."""
    source_root = next(
        (
            candidate
            for candidate in (source.parents)
            if candidate.name in {"src", "contracts"}
        ),
        target_root,
    )
    src_root = destination / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    test_root = destination / "test" / "generated"
    test_root.mkdir(parents=True, exist_ok=True)

    pending = [source]
    copied: set[Path] = set()
    while pending:
        current = pending.pop()
        try:
            relative = current.relative_to(source_root)
            destination_file = src_root / relative
        except ValueError:
            relative = current.relative_to(target_root)
            # npm packages must remain at the isolated Foundry root because
            # remappings such as @openzeppelin/=node_modules/@openzeppelin/
            # resolve from there. Other dependency trees are staged under src/.
            if relative.parts and relative.parts[0] == "node_modules":
                destination_file = destination / relative
            else:
                destination_file = src_root / relative
        if current in copied:
            continue
        copied.add(current)
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, destination_file)

        text = current.read_text(encoding="utf-8")
        remappings = []
        remappings_file = target_root / "remappings.txt"
        if remappings_file.exists():
            for line in remappings_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                prefix, destination_path = line.split("=", 1)
                remappings.append((prefix, destination_path))
        for imported in _IMPORT_RE.findall(text):
            if imported.startswith("."):
                dependency = (current.parent / imported).resolve()
            elif imported.startswith("contracts/"):
                dependency = (target_root / imported).resolve()
            else:
                dependency = None
                for prefix, destination_path in sorted(remappings, key=lambda item: len(item[0]), reverse=True):
                    if imported.startswith(prefix):
                        suffix = imported[len(prefix):]
                        dependency = (target_root / destination_path / suffix).resolve()
                        break
                if dependency is None:
                    continue
            if dependency.is_file() and dependency not in copied:
                pending.append(dependency)

    remapping_lines = []
    for prefix, destination_path in remappings:
        # npm remapping destinations already include their root prefix. Do not
        # prepend node_modules again; doing so creates node_modules/node_modules/...
        # Non-npm dependencies copied into src/ need that staging prefix.
        if destination_path.startswith("node_modules/"):
            remapping_lines.append(f"{prefix}={destination_path}")
        else:
            remapping_lines.append(f"{prefix}=src/{destination_path}")
    remapping_literal = ", ".join(repr(item) for item in remapping_lines)
    (destination / "foundry.toml").write_text(
        '[profile.default]\n'
        'src = "src"\n'
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
        "\n".join(remapping_lines) + "\n",
        encoding="utf-8",
    )
    return test_root


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=cwd, text=True, capture_output=True, check=True
    ).stdout.strip()


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
    parser.add_argument("--expected-status", choices=("confirmed", "not_confirmed"), default="confirmed")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--allow-no-hypothesis", action="store_true", help="Record a no-hypothesis disposition as a completed measurement rather than failing the runner.")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--supplemental-file",
        action="append",
        default=[],
        help="Copy a target-relative file from another git ref using path@ref, for historical build repairs.",
    )
    args = parser.parse_args()

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
        dependency_materialization = _materialize_target_dependencies(project)
        print(
            "DEPENDENCY_MATERIALIZATION",
            dependency_materialization.get("status"),
            "manager=",
            dependency_materialization.get("package_manager"),
            "lockfile=",
            dependency_materialization.get("lockfile"),
            "confidence=",
            dependency_materialization.get("confidence"),
        )
        compiler = compile_state_effects(project, source)
        result = investigate_authorization(
            source,
            target=f"{args.target_repo}@{args.target_ref}",
            semantic_evidence=compiler.evidence,
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-AUTH-001"]
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
            payload["dependency_materialization"] = dependency_materialization
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

        if dependency_materialization.get("status") == "BLOCKED":
            hypothesis = hypotheses[0] if hypotheses else None
            experiment = next(
                (e for e in result.experiments if hypothesis and e.hypothesis_id == hypothesis.hypothesis_id),
                None,
            )
            execution = ExecutionResult(
                experiment_id=experiment.experiment_id if experiment else "dependency-materialization",
                target=str(source),
                command=tuple(dependency_materialization.get("command") or ()),
                exit_code=2,
                executed=False,
                tests_run=0,
                tests_failed=0,
                status="UNMEASURABLE",
                stdout=dependency_materialization.get("stdout", ""),
                stderr=dependency_materialization.get("detail", "Target dependencies could not be materialized."),
            )
            payload = {
                "target": f"{args.target_repo}@{args.target_ref}:{args.target_path}",
                "hypothesis_seeds": _json(getattr(result, "seeds", ())),
                "hypothesis": _json(hypothesis) if hypothesis else None,
                "experiment": _json(experiment) if experiment else None,
                "dependency_materialization": dependency_materialization,
                "blind_execution": _json(execution),
                "classification": "UNMEASURABLE",
                "finding_gate": "NOT_READY",
            }
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(_json(payload), indent=2) + "\n", encoding="utf-8")
            print("EXECUTION_STATUS UNMEASURABLE reason=dependency_materialization_blocked")
            return 2

        execution_project = Path(temp) / "execution-project"
        _prepare_isolated_foundry_project(checkout, source, execution_project)

        source_root = next(
            (
                candidate
                for candidate in source.parents
                if candidate.name in {"src", "contracts"}
            ),
            project,
        )
        source_relative = Path(source).relative_to(source_root)
        for hypothesis in hypotheses:
            experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
            contract = next(
                c for c in result.contracts
                if any(f.name == hypothesis.target_function for f in c.functions)
            )
            # The blind harness now deploys the modeled contract directly.
            # Avoid a separate forge-inspect preflight: Foundry's generated
            # constructor helper can fail before the actual experiment even
            # when the typed deployment is valid. Execution itself remains the
            # authoritative compilation/execution measurement.
            creation_bytecode = None
            output = test_path_for(execution_project, f"generated/{hypothesis.hypothesis_id}.t.sol")
            try:
                generated = generate_blind_authorization_test_from_experiment(
                    hypothesis,
                    experiment,
                    os.path.relpath(
                        execution_project / "src" / Path(contract.source).relative_to(source_root),
                        output.parent,
                    ).replace(os.sep, "/"),
                    contract.name,
                    output,
                    contract,
                )
            except ValueError as exc:
                # A missing constructor type is a modeling/execution-precondition
                # gap, not evidence about the target. Preserve it explicitly as
                # UNMEASURABLE instead of fabricating an ABI value or crashing the
                # benchmark before an evidence artifact can be written.
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
                print("EXECUTION_STATUS", execution.status, "reason=", execution.stderr)
                outcome = classify_authorization_blind_execution(hypothesis, execution)
                payload = {
                    "target": f"{args.target_repo}@{args.target_ref}:{args.target_path}",
                    "hypothesis_seeds": _json(getattr(result, "seeds", ())),
                    "hypothesis": _json(hypothesis),
                    "experiment": _json(experiment),
                    "dependency_materialization": dependency_materialization,
                    "blind_execution": _json(execution),
                    "classification": outcome.benchmark_status,
                    "finding_gate": "NOT_READY",
                }
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(
                        json.dumps(_json(payload), indent=2) + "\n",
                        encoding="utf-8",
                    )
                print(
                    f"{hypothesis.hypothesis_id}: status={execution.status} "
                    f"classification={outcome.benchmark_status} evidence={outcome.evidence.evidence_id}"
                )
                return 2
            # Preserve the exact generated source outside the temporary isolated
            # project so the workflow artifact contains what Foundry actually ran.
            # Keep this adjacent to the structured campaign JSON output.
            if args.output:
                artifact_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", hypothesis.hypothesis_id)
                generated_artifact = args.output.with_name(
                    f"authorization-campaign.generated-{artifact_id}.t.sol"
                )
                generated_artifact.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(generated, generated_artifact)
            execution = run_foundry_test(execution_project, generated, experiment.experiment_id, "blind")
            print("EXECUTION_STATUS", execution.status, "exit=", execution.exit_code, "tests=", execution.tests_run, "failed=", execution.tests_failed)
            print(execution.stdout)
            print(execution.stderr)
            # UNMEASURABLE is a legitimate measurement outcome; preserve it
            # instead of converting a compiler/precondition gap into a runner crash.
            outcome = classify_authorization_blind_execution(hypothesis, execution)
            print(
                f"{hypothesis.hypothesis_id}: status={execution.status} "
                f"classification={outcome.benchmark_status} evidence={outcome.evidence.evidence_id}"
            )
            if outcome.benchmark_status != args.expected_status:
                return 2
            payload={"target":f"{args.target_repo}@{args.target_ref}:{args.target_path}","hypothesis_seeds":_json(getattr(result, "seeds", ())),"hypothesis":_json(hypothesis),"experiment":_json(experiment),"dependency_materialization":dependency_materialization,"blind_execution":_json(execution),"classification":outcome.benchmark_status,"finding_gate":"CONFIRMED_ONLY"}
            if args.require_ready and outcome.benchmark_status=="confirmed":
                isolated_source = execution_project / "src" / source_relative
                auth_context = "\n".join(
                    path.read_text(encoding="utf-8")
                    for path in sorted((execution_project / "src").rglob("*.sol"))
                )
                modifier = _auth_modifier(auth_context)
                print("AUTHORIZATION_CONTROL", modifier)
                if modifier is None: print("AUTHORIZATION_CAUSAL_CONTROL_UNAVAILABLE"); return 3
                original=_apply_auth_control(isolated_source,hypothesis.target_function,modifier)
                try:
                    patched_test=generated.with_name(generated.stem+"-patched.t.sol"); _patched_auth_test(generated,patched_test)
                    patched=run_foundry_test(execution_project,patched_test,hypothesis.hypothesis_id+":patched","patched")
                finally: isolated_source.write_text(original,encoding="utf-8")
                causal=execution.status=="FAIL" and patched.status=="PASS"
                reproduction=run_foundry_test(execution_project,generated,hypothesis.hypothesis_id+":reproduction","reproduction")
                original=_apply_auth_control(isolated_source,hypothesis.target_function,modifier)
                try:
                    repro_test=generated.with_name(generated.stem+"-reproduction-patched.t.sol"); _patched_auth_test(generated,repro_test)
                    repro_patched=run_foundry_test(execution_project,repro_test,hypothesis.hypothesis_id+":reproduction-patched","reproduction-patched")
                finally: isolated_source.write_text(original,encoding="utf-8")
                repro= reproduction.status=="FAIL" and repro_patched.status=="PASS"
                print("PATCHED_EXECUTION_STATUS", patched.status, "CAUSAL_VERIFICATION", causal)
                print("REPRODUCTION_EXECUTION_STATUS", reproduction.status, "REPRODUCTION_PATCHED_EXECUTION_STATUS", repro_patched.status, "REPRODUCTION_VERIFICATION", repro)
                payload.update({"authorization_control":modifier,"patched_execution":_json(patched),"causal_verification":{"state":"verified" if causal else "not_verified","chain_id":"causal:authorization-modifier-differential"},"reproduction_execution":_json(reproduction),"reproduction_patched_execution":_json(repro_patched),"reproduction_verification":{"state":"verified" if repro else "not_verified","chain_id":"reproduction:authorization-modifier-differential"},"finding_gate":"READY" if causal and repro and compiler.status != "source_dependency_closure_incomplete" else "NOT_READY"})
                if args.output:
                    args.output.parent.mkdir(parents=True,exist_ok=True)
                    args.output.write_text(json.dumps(_json(payload),indent=2)+"\n",encoding="utf-8")
                if not (causal and repro): return 4
            if args.output:
                args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(_json(payload),indent=2)+"\n",encoding="utf-8")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
