from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import solcx
    from semantic_version import Version, NpmSpec
except ImportError:  # surfaced as an explicit capability status by the caller
    solcx = None
    Version = NpmSpec = None

MAX_DIAGNOSTIC_CHARS = 6000


def _redact(text: str) -> str:
    text = re.sub(r"(?i)(token|secret|password|api[_-]?key)(\s*[=:]\s*)[^\s,;]+", r"\1\2[REDACTED]", text)
    return text[-MAX_DIAGNOSTIC_CHARS:]


def _remappings(project: Path) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for name in ("remappings.txt", "foundry.toml"):
        try:
            lines = (project / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            candidates = [line] if name == "remappings.txt" and "=" in line else []
            if name == "foundry.toml":
                candidates.extend(re.findall(r"""['"]([^'"]+=[^'"]+)['"]""", line))
            for candidate in candidates:
                prefix, target = candidate.split("=", 1)
                if prefix and target:
                    result.append((prefix, target))
    return sorted(set(result), key=lambda pair: len(pair[0]), reverse=True)


def _resolve_import(project: Path, importer: str, spec: str,
                    remappings: list[tuple[str, str]]) -> tuple[str, Path] | None:
    candidates: list[tuple[str, Path]] = []
    if spec.startswith("."):
        unit = str(PurePosixPath(importer).parent.joinpath(spec))
        unit = os.path.normpath(unit).replace("\\", "/")
        candidates.append((unit, project / unit))
    else:
        # Preserve package import identity for provenance, even though bytes live
        # under node_modules on disk.
        candidates.append((spec, project / "node_modules" / spec))
        candidates.append((spec, project / spec))
    for prefix, target in remappings:
        if spec.startswith(prefix):
            mapped = os.path.normpath(target + spec[len(prefix):]).replace("\\", "/")
            candidates.extend(((mapped, project / mapped),
                              (mapped, project / "node_modules" / mapped)))
    for unit, path in candidates:
        if path.is_file():
            return unit, path.resolve()
    return None


def _closure(project: Path, entry: Path) -> tuple[dict[str, str], list[str]]:
    remappings = _remappings(project)
    entry_unit = entry.resolve().relative_to(project.resolve()).as_posix()
    contents: dict[str, str] = {}
    unresolved: set[str] = set()
    pending: list[tuple[str, Path]] = [(entry_unit, entry.resolve())]
    import_re = re.compile(r"""\bimport\s+(?:[^;]*?\s+from\s+)?['"]([^'"]+)['"]\s*;""", re.S)

    def strip_comments(text: str) -> str:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.sub(r"//[^\n]*", "", text)

    while pending:
        unit, path = pending.pop()
        if unit in contents:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            unresolved.add(f"{unit}: source_unreadable")
            continue
        contents[unit] = source
        for spec in import_re.findall(strip_comments(source)):
            resolved = _resolve_import(project, unit, spec, remappings)
            if resolved is None:
                unresolved.add(f"{unit}: {spec}")
            elif resolved[0] not in contents:
                pending.append(resolved)
    return contents, sorted(unresolved)


def _compatible_version(contents: dict[str, str], requested: str | None = None) -> tuple[str | None, str]:
    if solcx is None or Version is None or NpmSpec is None:
        return None, "compiler_unavailable"
    constraints = []
    for unit, source in contents.items():
        for pragma in re.findall(r"\bpragma\s+solidity\s+([^;]+);", source):
            expression = pragma.strip().replace(" ", " ")
            try:
                constraints.append((unit, NpmSpec(expression)))
            except ValueError:
                return None, f"unsupported_pragma:{unit}:{expression}"
    try:
        installed = {str(v) for v in solcx.get_installed_solc_versions()}
        available = {str(v) for v in solcx.get_installable_solc_versions()}
    except Exception:
        installed, available = set(), set()
    candidates = sorted(available | installed, key=Version, reverse=True)
    if requested:
        candidates = [requested] if requested in candidates else []
    compatible = []
    for version in candidates:
        parsed = Version.coerce(version)
        if all(spec.match(parsed) for _, spec in constraints):
            compatible.append(version)
    if not compatible:
        return None, "unsatisfiable_pragma_intersection"
    return compatible[0], "ok"


def compile_standard_json(project: Path, entry: Path) -> dict[str, Any]:
    """Compile explicit source/import closure without loading target build configuration."""
    if solcx is None:
        return {"status": "compiler_unavailable", "solc_version_used": None,
                "errors_count": 0, "fatal_errors": [], "sources_parsed": [],
                "target_source_present": False, "stderr_excerpt": "py-solc-x is not installed",
                "process_exit_status": None, "unresolved_imports": [],
                "compiler_command": ["solcx.compile_standard"]}
    try:
        contents, unresolved = _closure(project.resolve(), entry.resolve())
    except (OSError, ValueError) as exc:
        return {"status": "source_closure_failed", "solc_version_used": None,
                "errors_count": 0, "fatal_errors": [], "sources_parsed": [],
                "target_source_present": False, "stderr_excerpt": _redact(str(exc)),
                "process_exit_status": None, "unresolved_imports": [],
                "compiler_command": ["solcx.compile_standard"]}
    if unresolved:
        return {"status": "source_dependency_closure_incomplete", "solc_version_used": None,
                "errors_count": 0, "fatal_errors": [], "sources_parsed": [],
                "target_source_present": entry.resolve().relative_to(project.resolve()).as_posix() in contents,
                "stderr_excerpt": "", "process_exit_status": None,
                "unresolved_imports": unresolved, "source_dependency_count": len(contents),
                "compiler_command": ["solcx.compile_standard"]}
    requested = None
    # A literal version in config is only a hint, not authority over source pragmas.
    config = project / "hardhat.config.js"
    if config.is_file():
        try:
            match = re.search(r"""solidity\s*:\s*['"]([0-9]+\.[0-9]+\.[0-9]+)['"]""", config.read_text(encoding="utf-8"))
            requested = match.group(1) if match else None
        except OSError:
            pass
    version, version_status = _compatible_version(contents, requested)
    if version is None and requested:
        # A config hint that is not compatible/available must not force failure if
        # another compiler version satisfies the entire closure.
        version, version_status = _compatible_version(contents, None)
    if version is None:
        return {"status": version_status, "solc_version_used": None, "errors_count": 0,
                "fatal_errors": [], "sources_parsed": [], "target_source_present": False,
                "stderr_excerpt": f"No installed/downloadable solc satisfies the full source closure ({version_status}).",
                "process_exit_status": None, "unresolved_imports": [],
                "source_dependency_count": len(contents), "compiler_command": ["solcx.compile_standard"]}
    try:
        if version not in {str(v) for v in solcx.get_installed_solc_versions()}:
            solcx.install_solc(version, show_progress=False)
        solcx.set_solc_version(version)
    except Exception as exc:
        return {"status": "compiler_unavailable", "solc_version_used": version, "errors_count": 0,
                "fatal_errors": [], "sources_parsed": [], "target_source_present": False,
                "stderr_excerpt": _redact(f"Unable to provision solc {version}: {exc}"),
                "process_exit_status": None, "unresolved_imports": [],
                "source_dependency_count": len(contents), "compiler_command": ["solcx.compile_standard", "--version", version]}
    input_json = {
        "language": "Solidity",
        "sources": {unit: {"content": source} for unit, source in contents.items()},
        "settings": {"outputSelection": {"*": {"": ["ast"], "*": []}}},
    }
    try:
        output = solcx.compile_standard(input_json, solc_version=version, allow_paths=str(project.resolve()))
    except Exception as exc:
        message = _redact(str(exc))
        return {"status": "compile_failed", "solc_version_used": version, "errors_count": 1,
                "fatal_errors": [message], "sources_parsed": [], "target_source_present": False,
                "stderr_excerpt": message, "process_exit_status": None, "unresolved_imports": [],
                "source_dependency_count": len(contents), "compiler_command": ["solcx.compile_standard", "--version", version]}
    errors = output.get("errors", []) if isinstance(output, dict) else []
    fatal = [item for item in errors if isinstance(item, dict) and item.get("severity") == "error"]
    parsed = output.get("sources", {}) if isinstance(output, dict) else {}
    ast_sources = sorted(unit for unit, item in parsed.items()
                         if isinstance(item, dict) and isinstance(item.get("ast"), dict))
    entry_unit = entry.resolve().relative_to(project.resolve()).as_posix()
    target_present = entry_unit in ast_sources
    status = "compile_failed" if fatal else ("success" if target_present else "no_ast_for_source")
    diagnostic_text = "\n".join(str(item.get("formattedMessage", item.get("message", "")))
                                 for item in errors if isinstance(item, dict))
    return {"status": status, "solc_version_used": version, "errors_count": len(errors),
            "fatal_errors": fatal, "sources_parsed": ast_sources, "target_source_present": target_present,
            "stderr_excerpt": _redact(diagnostic_text), "process_exit_status": 0 if not fatal else 1,
            "unresolved_imports": [], "source_dependency_count": len(contents),
            "compiler_command": ["solcx.compile_standard", "--version", version],
            "output": output, "input": input_json}
