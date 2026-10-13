from pathlib import Path

from cydra.compiler_state import (
    _compiler_version_attempted,
    _source_ast_status,
    _stderr_excerpt,
)


def test_compiler_version_uses_explicit_foundry_setting_on_failure(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "foundry.toml").write_text(
        '[profile.default]\nsolc = "0.8.25"\n', encoding="utf-8"
    )
    source = project / "src" / "Vault.sol"
    source.parent.mkdir()
    source.write_text("pragma solidity ^0.8.25; contract Vault {}", encoding="utf-8")

    assert _compiler_version_attempted(project, source, "compiler failed") == "0.8.25"


def test_compiler_version_uses_exact_pragma_when_no_version_is_configured(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "Vault.sol"
    source.write_text("pragma solidity 0.8.25; contract Vault {}", encoding="utf-8")

    assert _compiler_version_attempted(project, source) == "0.8.25"


def test_stderr_excerpt_is_bounded_to_first_lines_and_characters():
    stderr = "\n".join(f"compiler error line {index}" for index in range(100))

    excerpt = _stderr_excerpt(stderr, max_lines=3, max_chars=1000)

    assert excerpt.splitlines() == [
        "compiler error line 0",
        "compiler error line 1",
        "compiler error line 2",
    ]


def test_ast_status_explicitly_reports_failure_without_build_info():
    assert _source_ast_status(0, False, 0) == "not_produced"
    assert _source_ast_status(1, False, 1) == "source_present_without_ast"
    assert _source_ast_status(1, True, 1) == "produced"
