from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .compiler_standard_json import compile_standard_json


def compile_hardhat_direct(project: Path, source: Path) -> Any:
    """Direct-solc implementation for Hardhat-shaped repositories; never executes config."""
    from .compiler_state import (
        CompilerEvidenceResult,
        extract_constraints_from_build_info,
        extract_state_effects_from_build_info,
    )
    raw = compile_standard_json(project, source)
    output = raw.get("output")
    if not isinstance(output, dict):
        status = raw.get("status", "compile_failed")
        return CompilerEvidenceResult(
            (), (), True, status, tuple(raw.get("compiler_command", ())),
            json.dumps({"errors_count": raw.get("errors_count", 0),
                        "fatal_errors": raw.get("fatal_errors", [])})[:6000],
            str(raw.get("stderr_excerpt", ""))[:6000], (),
            (raw["solc_version_used"],) if raw.get("solc_version_used") else (),
            0, len(raw.get("sources_parsed", [])), bool(raw.get("target_source_present")),
            int(raw.get("source_dependency_count", 0)),
            tuple(raw.get("unresolved_imports", ())),
        )
    # Reuse the existing AST extractors by adapting Standard JSON output to the
    # minimal build-info envelope they already consume.
    payload = {"input": raw.get("input", {}), "output": output,
               "solcVersion": raw.get("solc_version_used")}
    entry_unit = source.resolve().relative_to(project.resolve()).as_posix()
    ast_sources = output.get("sources", {})
    if not isinstance(ast_sources, dict):
        ast_sources = {}
    source_allowlist = {
        key for key, value in ast_sources.items()
        if isinstance(key, str) and isinstance(value, dict) and isinstance(value.get("ast"), dict)
    }
    with tempfile.TemporaryDirectory(prefix="cydra-solc-json-") as directory:
        build_info = Path(directory) / "standard-json.json"
        build_info.write_text(json.dumps(payload), encoding="utf-8")
        evidence = extract_state_effects_from_build_info(build_info, source, project, source_allowlist)
        constraints = extract_constraints_from_build_info(build_info, source, project, source_allowlist)
    status = raw.get("status", "compile_failed")
    if status == "success" and not evidence and not constraints:
        status = "ast_present_no_supported_evidence"
    return CompilerEvidenceResult(
        evidence, constraints, True, status, tuple(raw.get("compiler_command", ())),
        json.dumps({"errors_count": raw.get("errors_count", 0),
                    "fatal_errors": raw.get("fatal_errors", [])})[:6000],
        str(raw.get("stderr_excerpt", ""))[:6000], (),
        (raw["solc_version_used"],) if raw.get("solc_version_used") else (),
        0, len(raw.get("sources_parsed", [])), bool(raw.get("target_source_present")),
        int(raw.get("source_dependency_count", 0)), tuple(raw.get("unresolved_imports", ())),
    )
