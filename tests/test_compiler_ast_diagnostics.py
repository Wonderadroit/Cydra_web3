import json
from pathlib import Path

from cydra.compiler_state import _build_info_ast_diagnostics


def _build_info(path: Path, sources: dict) -> Path:
    path.write_text(json.dumps({"output": {"sources": sources}}), encoding="utf-8")
    return path


def test_ast_diagnostics_distinguish_ast_from_empty_relationships(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "src" / "Intent.sol"
    source.parent.mkdir()
    source.write_text("pragma solidity ^0.8.20; contract Intent {}", encoding="utf-8")
    info = _build_info(
        tmp_path / "build-info.json",
        {"src/Intent.sol": {"id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}}},
    )

    assert _build_info_ast_diagnostics((info,), source, project) == (1, True)


def test_ast_diagnostics_distinguish_matched_source_without_ast(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "src" / "Intent.sol"
    source.parent.mkdir()
    source.write_text("pragma solidity ^0.8.20; contract Intent {}", encoding="utf-8")
    info = _build_info(tmp_path / "build-info.json", {"src/Intent.sol": {"id": 0}})

    assert _build_info_ast_diagnostics((info,), source, project) == (1, False)


def test_ast_diagnostics_report_no_matching_source(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "src" / "Intent.sol"
    source.parent.mkdir()
    source.write_text("pragma solidity ^0.8.20; contract Intent {}", encoding="utf-8")
    info = _build_info(
        tmp_path / "build-info.json",
        {"src/Other.sol": {"id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}}},
    )

    assert _build_info_ast_diagnostics((info,), source, project) == (0, False)
