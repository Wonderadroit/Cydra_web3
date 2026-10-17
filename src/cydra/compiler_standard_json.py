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


def _persist_solc_diagnostics(project: Path, input_json: dict[str, Any], errors: list[Any]) -> None:
    """Persist source-unit keys and compiler errors together for reproducible diagnosis."""
    root = Path(os.environ.get("CYDRA_SOLC_DIAGNOSTIC_DIR", project / ".cydra-diagnostics"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "solc-input-keys.json").write_text(
        json.dumps(sorted(input_json.get("sources", {}).keys()), indent=2) + "\n", encoding="utf-8"
    )
    (root / "solc-errors.json").write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")


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


def _closure(project: Path, entry: Path) -> tuple[dict[str, str], list[str], dict[str, str]]:
    remappings = _remappings(project)
    entry_unit = entry.resolve().relative_to(project.resolve()).as_posix()
    contents: dict[str, str] = {}
    source_paths: dict[str, str] = {}
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
        source_paths[unit] = str(path.resolve())
        for spec in import_re.findall(strip_comments(source)):
            resolved = _resolve_import(project, unit, spec, remappings)
            # A package source-unit name (e.g. @sample/pkg/A.sol) need not mirror
            # its on-disk node_modules path. Solc resolves a relative import from
            # the source-unit name, while the bytes can be read relative to the
            # physical importing file. Preserve the former and use the latter.
            if resolved is None and spec.startswith("."):
                relative_unit = os.path.normpath(
                    str(PurePosixPath(unit).parent.joinpath(spec))
                ).replace("\\\\", "/")
                relative_path = (path.parent / spec).resolve()
                if relative_path.is_file():
                    resolved = (relative_unit, relative_path)
            if resolved is None:
                unresolved.add(f"{unit}: {spec}")
            elif resolved[0] not in contents:
                pending.append(resolved)
    return contents, sorted(unresolved), source_paths


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
    # Query installed and downloadable versions independently. Failure to reach the
    # release catalogue must not erase already-installed compilers or be reported
    # as a mathematically impossible pragma intersection.
    discovery_errors = []
    try:
        installed = {str(v) for v in solcx.get_installed_solc_versions()}
    except Exception:
        installed = set()
        discovery_errors.append("installed")
    try:
        available = {str(v) for v in solcx.get_installable_solc_versions()}
    except Exception:
        available = set()
        discovery_errors.append("installable")
    all_candidates = installed | available
    candidates = sorted(all_candidates, key=Version, reverse=True)
    if requested:
        candidates = [requested] if requested in candidates else []
    compatible = []
    for version in candidates:
        parsed = Version.coerce(version)
        if all(spec.match(parsed) for _, spec in constraints):
            compatible.append(version)
    if not compatible:
        if not all_candidates:
            if discovery_errors:
                return None, "compiler_version_discovery_failed"
            return None, "compiler_unavailable"
        if requested and requested not in all_candidates:
            return None, "requested_compiler_unavailable"
        return None, "unsatisfiable_pragma_intersection"
    return compatible[0], "ok"


def compile_standard_json(project: Path, entry: Path) -> dict[str, Any]:
    """Compile explicit source/import closure without loading target build configuration."""
    if solcx is None:
        return {"status": "compiler_unavailable", "solc_version_used": None,
                "errors_count": 0, "fatal_errors": [], "sources_parsed": [],
                "target_source_present": False, "stderr_excerpt": "py-solc-x is not installed",
                "process_exit_status": None, "unresolved_imports": [],
                "compiler_command": ["solcx.compile_standard"], "source_paths": {}}
    try:
        contents, unresolved, source_paths = _closure(project.resolve(), entry.resolve())
    except (OSError, ValueError) as exc:
        return {"status": "source_closure_failed", "solc_version_used": None,
                "errors_count": 0, "fatal_errors": [], "sources_parsed": [],
                "target_source_present": False, "stderr_excerpt": _redact(str(exc)),
                "process_exit_status": None, "unresolved_imports": [],
                "compiler_command": ["solcx.compile_standard"]}
    closure_status = "source_dependency_closure_incomplete" if unresolved else "complete"
    requested = None
    # A literal version in config is only a hint, not authority over source pragmas.
    config = project / "hardhat.config.js"
    if config.is_file():
        try:
            config_text = config.read_text(encoding="utf-8")
            match = re.search(r"""solidity\b[\s\S]{0,500}?version\s*:\s*['"]([0-9]+\.[0-9]+\.[0-9]+)['"]""", config_text)
            if not match:
                match = re.search(r"""solidity\s*:\s*['"]([0-9]+\.[0-9]+\.[0-9]+)['"]""", config_text)
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
        "settings": {
            **({"remappings": [f"{prefix}={target}" for prefix, target in _remappings(project.resolve())]}
               if _remappings(project.resolve()) else {}),
            "outputSelection": {"*": {"": ["ast"], "*": []}},
        },
    }
    # Persist the exact source-unit keys before invoking solc; errors are written
    # beside them after parsing the compiler response, including failure responses.
    _persist_solc_diagnostics(project.resolve(), input_json, [])
    try:
        output = solcx.compile_standard(input_json, solc_version=version, allow_paths=str(project.resolve()))
    except Exception as exc:
        # py-solc-x can raise for fatal diagnostics while retaining Standard JSON
        # on stdout_data. Preserve partial source ASTs when the compiler emitted them.
        raw_stdout = getattr(exc, "stdout_data", None)
        if isinstance(raw_stdout, bytes):
            raw_stdout = raw_stdout.decode("utf-8", errors="replace")
        try:
            output = json.loads(raw_stdout) if isinstance(raw_stdout, str) else None
        except json.JSONDecodeError:
            output = None
        if not isinstance(output, dict):
            message = _redact(str(exc))
            _persist_solc_diagnostics(project.resolve(), input_json, [{"severity": "error", "message": message}])
            return {"status": "compile_failed", "closure_status": closure_status,
                    "solc_version_used": version, "errors_count": 1,
                    "fatal_errors": [{"severity": "error", "message": message}], "sources_parsed": [], "target_source_present": False,
                    "stderr_excerpt": message, "process_exit_status": None, "unresolved_imports": unresolved,
                    "source_dependency_count": len(contents), "compiler_command": ["solcx.compile_standard", "--version", version],
                    "input": input_json, "source_paths": source_paths}
    errors = output.get("errors", []) if isinstance(output, dict) else []
    fatal = [item for item in errors if isinstance(item, dict) and item.get("severity") == "error"]
    _persist_solc_diagnostics(project.resolve(), input_json, errors if isinstance(errors, list) else [])
    parsed = output.get("sources", {}) if isinstance(output, dict) else {}
    ast_sources = sorted(unit for unit, item in parsed.items()
                         if isinstance(item, dict) and isinstance(item.get("ast"), dict))
    entry_unit = entry.resolve().relative_to(project.resolve()).as_posix()
    target_present = entry_unit in ast_sources
    status = "compile_failed" if fatal else ("success" if target_present else "no_ast_for_source")
    diagnostic_text = "\n".join(str(item.get("formattedMessage", item.get("message", "")))
                                 for item in errors if isinstance(item, dict))
    return {"status": status, "closure_status": closure_status, "solc_version_used": version, "errors_count": len(errors),
            "fatal_errors": fatal, "sources_parsed": ast_sources, "target_source_present": target_present,
            "stderr_excerpt": _redact(diagnostic_text), "process_exit_status": 0 if not fatal else 1,
            "unresolved_imports": unresolved, "source_dependency_count": len(contents),
            "compiler_command": ["solcx.compile_standard", "--version", version],
            "output": output, "input": input_json, "source_paths": source_paths}
