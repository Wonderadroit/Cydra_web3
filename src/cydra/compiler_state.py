from __future__ import annotations

import json
import os
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


def _source_asts(payload: dict[str, Any]) -> tuple[tuple[str, dict[str, Any]], ...]:
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
        and isinstance(source_payload, dict)
        and isinstance(source_payload.get("ast"), dict)
    )


def extract_state_effects_from_build_info(build_info: Path, source: Path, project: Path) -> tuple[SemanticRelationshipEvidence, ...]:
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    evidence: list[SemanticRelationshipEvidence] = []
    for source_key, ast in _source_asts(payload):
        evidence.extend(extract_ast_relationships(ast, source_key))
    # A project can emit multiple build-info records that repeat imported sources.
    unique: dict[tuple[Any, ...], SemanticRelationshipEvidence] = {}
    for item in evidence:
        key = (item.source, item.function, item.relation, item.target, item.ast_node_id,
               item.function_ast_node_id, item.target_ast_node_id, item.source_location)
        unique.setdefault(key, item)
    return tuple(unique.values())


def extract_constraints_from_build_info(build_info: Path, source: Path, project: Path) -> tuple[ConstraintEvidence, ...]:
    payload = json.loads(build_info.read_text(encoding="utf-8"))
    evidence: list[ConstraintEvidence] = []
    source_asts = _source_asts(payload)
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
    for build_file in build_files:
        try:
            payload = json.loads(build_file.read_text(encoding="utf-8"))
            version = payload.get("solcVersion")
            if isinstance(version, str):
                versions.add(version)
            evidence.extend(extract_state_effects_from_build_info(build_file, source_path, project_path))
            constraints.extend(extract_constraints_from_build_info(build_file, source_path, project_path))
        except (OSError, json.JSONDecodeError):
            continue
    # Hardhat may produce multiple build-info records that repeat dependency ASTs.
    unique_evidence: dict[tuple[Any, ...], SemanticRelationshipEvidence] = {}
    for item in evidence:
        key = (item.source, item.function, item.relation, item.target, item.ast_node_id,
               item.function_ast_node_id, item.target_ast_node_id, item.source_location)
        unique_evidence.setdefault(key, item)
    unique_constraints = tuple(dict.fromkeys(constraints))
    if not build_files:
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
        return _compile_hardhat_state_effects(project_path, source_path)

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
        for build_file in build_files:
            try:
                payload = json.loads(build_file.read_text(encoding="utf-8"))
                version = payload.get("solcVersion")
                if isinstance(version, str):
                    versions.add(version)
                evidence.extend(extract_state_effects_from_build_info(build_file, source_path, project_path))
                constraints.extend(extract_constraints_from_build_info(build_file, source_path, project_path))
            except (OSError, json.JSONDecodeError):
                continue
        if not build_files:
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
            source_ast_found,
        )
