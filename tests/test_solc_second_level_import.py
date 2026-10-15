import json
from pathlib import Path

import pytest
import solcx

from cydra.compiler_standard_json import compile_standard_json


def _write_fixture(project: Path) -> tuple[Path, dict[str, str]]:
    entry = project / "contracts" / "Entry.sol"
    package = project / "node_modules" / "@sample" / "contracts"
    a_file = package / "access" / "A.sol"
    b_file = package / "utils" / "B.sol"
    entry.parent.mkdir(parents=True)
    a_file.parent.mkdir(parents=True)
    b_file.parent.mkdir(parents=True)
    entry.write_text(
        'pragma solidity ^0.8.20; import "@sample/contracts/access/A.sol"; '
        'contract Entry is A { function value() external pure returns (uint256) { return 7; } }\n',
        encoding="utf-8",
    )
    a_file.write_text(
        'pragma solidity ^0.8.20; import "../utils/B.sol"; contract A is B {}\n',
        encoding="utf-8",
    )
    b_file.write_text(
        'pragma solidity ^0.8.20; contract B { function baseValue() public pure returns (uint256) { return 1; } }\n',
        encoding="utf-8",
    )
    return entry, {
        "contracts/Entry.sol": entry.read_text(encoding="utf-8"),
        "@sample/contracts/access/A.sol": a_file.read_text(encoding="utf-8"),
        "@sample/contracts/utils/B.sol": b_file.read_text(encoding="utf-8"),
    }


def _compile_output(input_json: dict, version: str) -> dict:
    try:
        return solcx.compile_standard(input_json, solc_version=version)
    except Exception as exc:
        raw = getattr(exc, "stdout_data", None)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        raise


def test_real_solc_second_level_import_and_missing_key_negative_case(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    entry, sources = _write_fixture(project)
    diagnostics = tmp_path / "diagnostics"
    monkeypatch.setenv("CYDRA_SOLC_DIAGNOSTIC_DIR", str(diagnostics))

    # Positive case: the real source walker feeds the real Standard JSON compiler.
    result = compile_standard_json(project, entry)
    assert result["status"] == "success", result.get("fatal_errors")
    assert result["closure_status"] == "complete"
    assert "@sample/contracts/utils/B.sol" in result["sources_parsed"]
    assert json.loads((diagnostics / "solc-input-keys.json").read_text()) == sorted(sources)
    recorded_errors = json.loads((diagnostics / "solc-errors.json").read_text())
    assert not any(item.get("severity") == "error" for item in recorded_errors)

    # Negative control: same three files, but B is deliberately keyed incorrectly.
    bad_sources = dict(sources)
    bad_sources["renamed/B.sol"] = bad_sources.pop("@sample/contracts/utils/B.sol")
    bad_input = {
        "language": "Solidity",
        "sources": {key: {"content": value} for key, value in bad_sources.items()},
        "settings": {"outputSelection": {"*": {"": ["ast"], "*": []}}},
    }
    output = _compile_output(bad_input, result["solc_version_used"])
    errors = output.get("errors", [])
    messages = "\\n".join(str(item.get("formattedMessage", item.get("message", ""))) for item in errors)
    assert any(item.get("severity") == "error" for item in errors), messages
    assert "Source not found" in messages
    assert "@sample/contracts/utils/B.sol" in messages
    assert "@sample/contracts/utils/B.sol" not in bad_input["sources"]
