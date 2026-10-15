from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import tempfile
import shutil
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ast_dataflow import SemanticRelationshipEvidence, extract_ast_relationships
from .compiler_constraints import ConstraintEvidence, collect_ast_declarations, extract_parameter_constraints


@dataclass(frozen=True)
class CompilerEvidenceResult:
    evidence: tuple[SemanticRelationshipEvidence, ...]
    constraints: tuple[ConstraintEvidence, ...]
    executed: bool
    status: str
    command: tuple[str, ...]
    stdout: str
    stderr: str
    build_info_files: tuple[str, ...] = ()
    compiler_versions: tuple[str, ...] = ()
    build_info_count: int = 0
    matched_source_count: int = 0
    source_ast_found: bool = False
    source_dependency_count: int = 0
    unresolved_imports: tuple[str, ...] = ()
    closure_status: str = "complete"


def _source_keys(payload: dict[str, Any], source: Path, project: Path) -> tuple[tuple[str, dict[str, Any]], ...]:
    output = payload.get("output")
    if not isinstance(output, dict):
        return ()
    sources = output.get("sources")
    if not isinstance(sources, dict):
        return ()
    relative = os.path.relpath(source.resolve(), project.resolve()).replace(os.sep, "/")
    candidates: list[tuple[str, dict[str, Any]]] = []
    for key, value in sources.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        normalized = key.replace("\\", "/")
        if normalized == relative or normalized.endswith("/" + relative):
            candidates.append((key, value))
    return tuple(candidates)


def _project_remappings(project: Path) -> tuple[tuple[str, str], ...]:
    mappings: list[tuple[str, str]] = []
    for path in (project / "remappings.txt", project / "foundry.toml"):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for raw in source.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            candidates = [line] if "=" in line and not line.startswith("[") else []
            if path.name == "foundry.toml":
                candidates.extend(re.findall(r"""['"]([^'"]+=[^'"]+)['"]""", line))
            for candidate in candidates:
                prefix, target = candidate.split("=", 1)
                if prefix and target:
                    mappings.append((prefix, target))
    return tuple(sorted(set(mappings), key=lambda item: len(item[0]), reverse=True))


def _source_dependency_closure(
    payload: dict[str, Any], source: Path, project: Path
) -> tuple[set[str], tuple[str, ...]]:
    """Return the exact source/import closure for the requested entry AST."""
    output = payload.get("output")
    sources = output.get("sources") if isinstance(output, dict) else None
    input_payload = payload.get("input")
    input_sources = input_payload.get("sources") if isinstance(input_payload, dict) else None
    if not isinstance(sources, dict):
        return set(), ()
    relative = os.path.relpath(source.resolve(), project.resolve()).replace(os.sep, "/")
    source_keys = [key for key in sources if isinstance(key, str)]
    normalized_keys = {
        posixpath.normpath(key.replace("\\", "/")): key
        for key in source_keys
    }
    starts = {
        key for key in source_keys
        if posixpath.normpath(key.replace("\\", "/")) == relative
        or posixpath.normpath(key.replace("\\", "/")).endswith("/" + relative)
    }
    if not starts:
        return set(), ()
    remappings = _project_remappings(project)
    import_re = re.compile(r"""\bimport\s+(?:[^;]*?\s+from\s+)?['"]([^'"]+)['"]\s*;""", re.DOTALL)
    # Ignore Solidity line/block comments before import discovery. Otherwise a
    # deliberately disabled import is treated as a required dependency and the
    # target closure is incorrectly marked incomplete.
    def without_comments(text: str) -> str:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return re.sub(r"//[^\n]*", "", text)
    closure: set[str] = set()
    unresolved: set[str] = set()
    pending = list(starts)

    def content_for(key: str) -> str:
        item = input_sources.get(key) if isinstance(input_sources, dict) else None
        if isinstance(item, dict) and isinstance(item.get("content"), str):
            return item["content"]
        candidate = project / key
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""

    def resolve(importer: str, spec: str) -> str | None:
        candidates: list[str] = []
        if spec.startswith("."):
            candidates.append(posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec)))
        candidates.append(spec)
        for prefix, target in remappings:
            if spec.startswith(prefix):
                suffix = spec[len(prefix):]
                mapped = posixpath.normpath(posixpath.join(target, suffix))
                candidates.extend((mapped, posixpath.join("node_modules", mapped)))
        candidates.append(posixpath.join("node_modules", spec))
        normalized = [posixpath.normpath(item.replace("\\", "/")) for item in candidates]
        for candidate in normalized:
            if candidate in normalized_keys:
                return normalized_keys[candidate]
        for candidate in normalized:
            matches = [raw for norm, raw in normalized_keys.items() if norm.endswith("/" + candidate)]
            if len(matches) == 1:
                return matches[0]
        # Some compiler inputs retain the bare import path while filesystem-based
        # resolution sees the package under node_modules; only accept unique matches.
        spec_normalized = posixpath.normpath(spec.replace("\\", "/"))
        matches = [raw for norm, raw in normalized_keys.items() if norm.endswith("/" + spec_normalized)]
        return matches[0] if len(matches) == 1 else None

    while pending:
        importer = pending.pop()
        if importer in closure:
            continue
        closure.add(importer)
        for spec in import_re.findall(without_comments(content_for(importer))):
            resolved = resolve(importer, spec)
            if resolved is None:
                unresolved.add(f"{importer}: {spec}")
            elif resolved not in closure:
                pending.append(resolved)
    return closure, tuple(sorted(unresolved))


def _source_asts(payload: dict[str, Any], source_allowlist: set[str] | None = None) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Return every compiler AST in this build unit, including imported base contracts.

    Authorization effects often live in inherited contracts rather than the concrete
    deployment entry file. Restricting extraction to the entry source silently drops
    those effects even when the compiler supplied their ASTs in the same build-info.
    """
    output = payload.get("output")
    sources = output.get("sources") if isinstance(output, dict) else None
    if not isinstance(sources, dict):
        return ()
    return tuple(
        (key, source_payload["ast"])
        for key, source_payload in sources.items()
        if isinstance(key, str)
        and (source_allowlist is None or key in source_allowlist)
        and isinstance(source_payload, dict)
        and isinstance(source_payload.get("ast"), dict)
    )


def _cross_source_call_diagnostics(
    source_asts: tuple[tuple[str, dict[str, Any]], ...],
    evidence: list[SemanticRelationshipEvidence],
) -> list[dict[str, Any]]:
    """Observe call resolution and write forms without changing extraction behavior."""
    functions: dict[int, tuple[dict[str, Any], str]] = {}
    states: dict[int, str] = {}
    source_local_functions: dict[str, set[int]] = {}
    for source_key, ast in source_asts:
        local_ids: set[int] = set()
        for node in _walk_ast_nodes(ast):
            node_id = node.get("id")
            if node.get("nodeType") == "FunctionDefinition" and isinstance(node_id, int):
                functions[node_id] = (node, source_key)
                local_ids.add(node_id)
            if (node.get("nodeType") == "VariableDeclaration"
                    and node.get("stateVariable") is True
                    and node.get("mutability", "mutable") not in {"constant", "immutable"}
                    and isinstance(node_id, int) and isinstance(node.get("name"), str)):
                states[node_id] = node["name"]
        source_local_functions[source_key] = local_ids

    def walk(node: Any):
        if isinstance(node, dict):
            if isinstance(node.get("nodeType"), str):
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    def state_root(node: Any) -> str | None:
        if not isinstance(node, dict):
            return None
        kind = node.get("nodeType")
        if kind == "Identifier":
            ref = node.get("referencedDeclaration")
            return states.get(ref) if isinstance(ref, int) else None
        if kind in {"IndexAccess", "IndexRangeAccess"}:
            return state_root(node.get("baseExpression"))
        if kind == "MemberAccess":
            return state_root(node.get("expression"))
        return None

    rows: list[dict[str, Any]] = []
    for source_key, ast in source_asts:
        for caller in walk(ast):
            if caller.get("nodeType") != "FunctionDefinition" or not isinstance(caller.get("id"), int):
                continue
            caller_id = caller["id"]
            caller_name = caller.get("name") or caller.get("kind") or "anonymous"
            caller_body = caller.get("body")
            if not isinstance(caller_body, dict):
                continue
            for call in walk(caller_body):
                if call.get("nodeType") != "FunctionCall":
                    continue
                expression = call.get("expression")
                if not isinstance(expression, dict) or expression.get("nodeType") != "Identifier":
                    continue
                callee_id = expression.get("referencedDeclaration")
                if not isinstance(callee_id, int):
                    continue
                found = functions.get(callee_id)
                in_global_map = found is not None
                callee = found[0] if found else {}
                callee_source = found[1] if found else None
                callee_body = callee.get("body") if isinstance(callee, dict) else None
                # This reflects whether the existing per-AST propagation loop can
                # enter this callee, not merely whether solc resolved its ID globally.
                callee_body_entered = (
                    in_global_map and callee_id in source_local_functions.get(source_key, set())
                    and isinstance(callee_body, dict)
                )
                write_forms: list[dict[str, Any]] = []
                writes_found: set[str] = set()
                if isinstance(callee_body, dict):
                    for item in walk(callee_body):
                        kind = item.get("nodeType")
                        if kind == "Assignment":
                            lhs = item.get("leftHandSide")
                            root = state_root(lhs)
                            if root:
                                writes_found.add(root)
                                lhs_kind = lhs.get("nodeType") if isinstance(lhs, dict) else None
                                write_forms.append({
                                    "form": "nested_index_assignment" if lhs_kind == "IndexAccess" else
                                            "member_assignment" if lhs_kind == "MemberAccess" else
                                            "simple_assignment" if lhs_kind == "Identifier" else
                                            "compound_lvalue_assignment",
                                    "target": root,
                                    "operator": item.get("operator"),
                                    "lhs_node_type": lhs_kind,
                                })
                        elif kind == "FunctionCall":
                            expr = item.get("expression")
                            if isinstance(expr, dict) and expr.get("nodeType") == "MemberAccess" and expr.get("memberName") == "push":
                                root = state_root(expr.get("expression"))
                                if root:
                                    writes_found.add(root)
                                    write_forms.append({
                                        "form": "array_push",
                                        "target": root,
                                        "member": "push",
                                        "expression_node_type": (expr.get("expression") or {}).get("nodeType")
                                            if isinstance(expr.get("expression"), dict) else None,
                                    })
                propagated = any(
                    item.function_ast_node_id == caller_id
                    and item.relation == "writes"
                    and (item.metadata or {}).get("propagated_from_internal_call")
                    for item in evidence
                )
                rows.append({
                    "caller": str(caller_name),
                    "caller_source": source_key,
                    "callee": str(callee.get("name") or callee.get("kind") or "unknown"),
                    "referenced_declaration": callee_id,
                    "in_global_map": in_global_map,
                    "callee_declaring_source": callee_source,
                    "callee_body_entered": bool(callee_body_entered),
                    "write_forms": write_forms,
                    "writes_found": sorted(writes_found),
                    "writes_propagated_to_caller": bool(propagated),
                    "call_source_location": call.get("src"),
                })
    return rows


def _walk_ast_nodes(node: Any):
    if isinstance(node, dict):
        if isinstance(node.get("nodeType"), str):
            yield node
        for value in node.values():
            yield from _walk_ast_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_ast_nodes(value)


def _persist_cross_source_call_diagnostics(rows: list[dict[str, Any]]) -> None:
    """Append unique diagnostic rows to the campaign artifact directory."""
    directory = os.environ.get("CYDRA_SOLC_DIAGNOSTIC_DIR")
    if not directory or not rows:
        return
    path = Path(directory) / "cross-source-call-resolution.json"
    existing: list[dict[str, Any]] = []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, list):
            existing = parsed
    except (OSError, json.JSONDecodeError):
        pass
    seen = {json.dumps(row, sort_keys=True) for row in existing}
    for row in rows:
        encoded = json.dumps(row, sort_keys=True)
        if encoded not in seen:
            existing.append(row)
            seen.add(encoded)
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def extract_state_effects_from_build_info(
    build_info: Path, source: Path, project: Path, source_allowlist: set[str] | None = None
) -> tuple[SemanticRelationshipEvidence, ...]:
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    source_asts = _source_asts(payload, source_allowlist)
    evidence: list[SemanticRelationshipEvidence] = []
    for source_key, ast in source_asts:
        evidence.extend(extract_ast_relationships(ast, source_key))
    # Diagnostics are observational only: they do not feed back into evidence.
    _persist_cross_source_call_diagnostics(_cross_source_call_diagnostics(source_asts, evidence))
    # A project can emit multiple build-info records that repeat imported sources.
    unique: dict[tuple[Any, ...], SemanticRelationshipEvidence] = {}
    for item in evidence:
        key = (item.source, item.function, item.relation, item.target, item.ast_node_id,
               item.function_ast_node_id, item.target_ast_node_id, item.source_location)
        unique.setdefault(key, item)
    return tuple(unique.values())


def extract_constraints_from_build_info(
    build_info: Path, source: Path, project: Path, source_allowlist: set[str] | None = None
) -> tuple[ConstraintEvidence, ...]:
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    evidence: list[ConstraintEvidence] = []
    source_asts = _source_asts(payload, source_allowlist)
    declarations = collect_ast_declarations([ast for _, ast in source_asts])
    for source_key, ast in source_asts:
        evidence.extend(extract_parameter_constraints(ast, source_key, declarations))
    return tuple(dict.fromkeys(evidence))


def _build_info_ast_diagnostics(
    build_files: tuple[Path, ...], source: Path, project: Path
) -> tuple[int, bool]:
    """Return matched source count and whether any matching source contains an AST."""
    matched_sources = 0
    ast_found = False
    for build_file in build_files:
        try:
            payload = json.loads(build_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for _source_key, source_payload in _source_keys(payload, source, project):
            matched_sources += 1
            if isinstance(source_payload.get("ast"), dict):
                ast_found = True
    return matched_sources, ast_found


def _has_lite_profile(project: Path) -> bool:
    config = project / "foundry.toml"
    try:
        return "[profile.lite]" in config.read_text(encoding="utf-8")
    except OSError:
        return False


def _is_hardhat_project(project: Path) -> bool:
    return (project / "package.json").is_file() and any(
        (project / name).is_file()
        for name in ("hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs")
    )


def _hardhat_build_info_root(project: Path) -> Path:
    """Resolve Hardhat's configured artifact directory, with common-path fallbacks."""
    artifacts_dir = "artifacts"
    for name in ("hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs"):
        config = project / name
        try:
            source = config.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        match = re.search(r"\bartifacts\s*:\s*['\"]([^'\"]+)['\"]", source)
        if match:
            artifacts_dir = match.group(1)
        break
    configured = Path(artifacts_dir)
    if not configured.is_absolute():
        configured = project / configured
    return configured / "build-info"


def _hardhat_commands(project: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if (project / "yarn.lock").is_file():
        return (
            ("yarn", "install", "--frozen-lockfile", "--non-interactive", "--ignore-scripts"),
            ("yarn", "hardhat", "compile", "--force"),
        )
    if (project / "package-lock.json").is_file():
        return (
            ("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"),
            ("npx", "--no-install", "hardhat", "compile", "--force"),
        )
    return (
        ("npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"),
        ("npx", "--no-install", "hardhat", "compile", "--force"),
    )


def _compile_hardhat_state_effects(project_path: Path, source_path: Path) -> CompilerEvidenceResult:
    """Compile a Hardhat project locally and consume its solc build-info ASTs."""
    install_command, compile_command = _hardhat_commands(project_path)
    installed = subprocess.run(
        install_command, cwd=project_path, text=True, capture_output=True, check=False
    )
    if installed.returncode != 0:
        return CompilerEvidenceResult(
            (), (), True, "dependency_install_failed", install_command,
            installed.stdout, installed.stderr,
        )

    build_info_root = _hardhat_build_info_root(project_path)
    shutil.rmtree(build_info_root, ignore_errors=True)
    completed = subprocess.run(
        compile_command, cwd=project_path, text=True, capture_output=True, check=False
    )
    build_files = tuple(sorted(build_info_root.rglob("*.json")))
    stdout = installed.stdout + "\n" + completed.stdout
    stderr = installed.stderr + "\n" + completed.stderr
    if completed.returncode != 0:
        return CompilerEvidenceResult(
            (), (), True, "compile_failed", compile_command, stdout, stderr,
            tuple(map(str, build_files)),
        )

    evidence: list[SemanticRelationshipEvidence] = []
    constraints: list[ConstraintEvidence] = []
    versions: set[str] = set()
    matched_source_count, source_ast_found = _build_info_ast_diagnostics(
        build_files, source_path, project_path
    )
    dependency_sources: set[str] = set()
    unresolved_imports: set[str] = set()
    for build_file in build_files:
        try:
            payload = json.loads(build_file.read_text(encoding="utf-8"))
            version = payload.get("solcVersion")
            if isinstance(version, str):
                versions.add(version)
            allowlist, unresolved = _source_dependency_closure(payload, source_path, project_path)
            if not allowlist:
                continue
            dependency_sources.update(allowlist)
            unresolved_imports.update(unresolved)
            evidence.extend(extract_state_effects_from_build_info(build_file, source_path, project_path, allowlist))
            constraints.extend(extract_constraints_from_build_info(build_file, source_path, project_path, allowlist))
        except (OSError, json.JSONDecodeError):
            continue
    # Hardhat may produce multiple build-info records that repeat dependency ASTs.
    unique_evidence: dict[tuple[Any, ...], SemanticRelationshipEvidence] = {}
    for item in evidence:
        key = (item.source, item.function, item.relation, item.target, item.ast_node_id,
               item.function_ast_node_id, item.target_ast_node_id, item.source_location)
        unique_evidence.setdefault(key, item)
    unique_constraints = tuple(dict.fromkeys(constraints))
    if unresolved_imports:
        status = "source_dependency_closure_incomplete"
    elif not build_files:
        status = "no_build_info_artifacts"
    elif unique_evidence or unique_constraints:
        status = "success"
    elif source_ast_found:
        status = "ast_present_no_supported_evidence"
    elif matched_source_count:
        status = "source_present_without_ast"
    else:
        status = "no_ast_for_source"
    return CompilerEvidenceResult(
        tuple(unique_evidence.values()), unique_constraints, True, status, compile_command,
        stdout, stderr, tuple(map(str, build_files)), tuple(sorted(versions)),
        len(build_files), matched_source_count, source_ast_found,
        len(dependency_sources), tuple(sorted(unresolved_imports)),
    )


def compile_state_effects(project: str | Path, source: str | Path) -> CompilerEvidenceResult:
    """Compile Foundry or Hardhat projects and consume compiler AST evidence.

    Compilation failure is a capability gap, not evidence that no state effect exists.
    """
    project_path = Path(project).resolve()
    source_path = Path(source).resolve()
    command = ("forge", "build", "--build-info")
    if not project_path.exists() or not source_path.exists():
        return CompilerEvidenceResult((), (), False, "input_missing", command, "", "project or source missing")
    if not (project_path / "foundry.toml").is_file() and _is_hardhat_project(project_path):
        from .compiler_hardhat_direct import compile_hardhat_direct
        return compile_hardhat_direct(project_path, source_path)

    with tempfile.TemporaryDirectory(prefix="cydra-build-info-", dir=project_path.parent) as temp:
        info_path = Path(temp)
        relative_source = os.path.relpath(source_path, project_path).replace(os.sep, "/")
        profile = ("--profile", "lite") if _has_lite_profile(project_path) else ()
        command = (
            "forge", "build", "--build-info", "--build-info-path", str(info_path),
            *profile, "--skip", "test", "--skip", "script", "--threads", "1", relative_source,
        )
        completed = subprocess.run(command, cwd=project_path, text=True, capture_output=True, check=False)
        build_files = tuple(sorted(info_path.rglob("*.json")))
        # Some npm/Hardhat Solidity targets are valid only under the Solidity
        # compiler's via-IR pipeline (typically because an ordinary pipeline
        # hits "Stack too deep"). Retry that compiler capability generically;
        # never reinterpret the failed first compile as semantic evidence.
        if completed.returncode != 0 and "Stack too deep" in completed.stderr and "--via-ir" not in command:
            retry_command = (
                "forge", "build", "--build-info", "--build-info-path", str(info_path),
                *profile, "--skip", "test", "--skip", "script", "--threads", "1",
                "--via-ir", "--optimize", "--optimizer-runs", "200", relative_source,
            )
            completed = subprocess.run(
                retry_command, cwd=project_path, text=True, capture_output=True, check=False
            )
            command = retry_command
            build_files = tuple(sorted(info_path.rglob("*.json")))
        if completed.returncode != 0:
            return CompilerEvidenceResult((), (), True, "compile_failed", command, completed.stdout, completed.stderr, tuple(map(str, build_files)))

        evidence: list[SemanticRelationshipEvidence] = []
        constraints: list[ConstraintEvidence] = []
        versions: set[str] = set()
        matched_source_count, source_ast_found = _build_info_ast_diagnostics(
            build_files, source_path, project_path
        )
        dependency_sources: set[str] = set()
        unresolved_imports: set[str] = set()
        for build_file in build_files:
            try:
                payload = json.loads(build_file.read_text(encoding="utf-8"))
                version = payload.get("solcVersion")
                if isinstance(version, str):
                    versions.add(version)
                allowlist, unresolved = _source_dependency_closure(payload, source_path, project_path)
                if not allowlist:
                    continue
                dependency_sources.update(allowlist)
                unresolved_imports.update(unresolved)
                evidence.extend(extract_state_effects_from_build_info(build_file, source_path, project_path, allowlist))
                constraints.extend(extract_constraints_from_build_info(build_file, source_path, project_path, allowlist))
            except (OSError, json.JSONDecodeError):
                continue
        if unresolved_imports:
            status = "source_dependency_closure_incomplete"
        elif not build_files:
            status = "no_build_info_artifacts"
        elif evidence or constraints:
            status = "success"
        elif source_ast_found:
            status = "ast_present_no_supported_evidence"
        elif matched_source_count:
            status = "source_present_without_ast"
        else:
            status = "no_ast_for_source"
        return CompilerEvidenceResult(
            tuple(evidence), tuple(constraints), True, status, command,
            completed.stdout, completed.stderr, tuple(map(str, build_files)),
            tuple(sorted(versions)), len(build_files), matched_source_count,
            source_ast_found, len(dependency_sources), tuple(sorted(unresolved_imports)),
        )
