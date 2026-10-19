import json
from pathlib import Path

import pytest

from cydra import compiler_standard_json as direct


def test_pragma_intersection_fails_closed(monkeypatch):
    monkeypatch.setattr(direct.solcx, "get_installed_solc_versions", lambda: [])
    monkeypatch.setattr(direct.solcx, "get_installable_solc_versions", lambda: ["0.8.26", "0.7.6"])
    contents = {
        "A.sol": "pragma solidity ^0.8.20; contract A {}",
        "B.sol": "pragma solidity ^0.7.0; contract B {}",
    }
    version, status = direct._compatible_version(contents)
    assert version is None
    assert status == "unsatisfiable_pragma_intersection"


def test_package_import_identity_is_preserved(tmp_path):
    from cydra.compiler_standard_json import _closure

    entry = tmp_path / "contracts" / "Entry.sol"
    entry.parent.mkdir()
    entry.write_text(
        'pragma solidity ^0.8.20; import "@acme/lib/Thing.sol"; contract Entry is Thing {}',
        encoding="utf-8",
    )
    package = tmp_path / "node_modules" / "@acme" / "lib" / "Thing.sol"
    package.parent.mkdir(parents=True)
    package.write_text("pragma solidity ^0.8.20; contract Thing {}", encoding="utf-8")

    sources, unresolved = _closure(tmp_path, entry)
    assert unresolved == []
    assert "@acme/lib/Thing.sol" in sources


def test_fatal_standard_json_diagnostics_preserve_partial_asts(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    entry = project / "Entry.sol"
    entry.write_text("pragma solidity ^0.8.20; contract Entry {}", encoding="utf-8")
    monkeypatch.setattr(direct, "_compatible_version", lambda contents, requested=None: ("0.8.26", "ok"))
    monkeypatch.setattr(direct.solcx, "get_installed_solc_versions", lambda: ["0.8.26"])
    monkeypatch.setattr(direct.solcx, "set_solc_version", lambda version: None)

    partial = {
        "errors": [{"severity": "error", "formattedMessage": "synthetic compile error"}],
        "sources": {"Entry.sol": {"id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}}},
    }

    class CompilerFailure(Exception):
        stdout_data = json.dumps(partial)

    monkeypatch.setattr(direct.solcx, "compile_standard", lambda *args, **kwargs: (_ for _ in ()).throw(CompilerFailure("compile failed")))
    result = direct.compile_standard_json(project, entry)

    assert result["status"] == "compile_failed"
    assert result["fatal_errors"]
    assert result["sources_parsed"] == ["Entry.sol"]
    assert result["target_source_present"] is True


def test_remapping_import_resolves_to_normalized_source_unit(tmp_path):
    from cydra.compiler_standard_json import _closure

    entry = tmp_path / "contracts" / "Entry.sol"
    entry.parent.mkdir()
    entry.write_text(
        'pragma solidity ^0.8.20; import "@local/Thing.sol"; contract Entry is Thing {}',
        encoding="utf-8",
    )
    (tmp_path / "remappings.txt").write_text("@local/=lib/\n", encoding="utf-8")
    dependency = tmp_path / "lib" / "Thing.sol"
    dependency.parent.mkdir()
    dependency.write_text("pragma solidity ^0.8.20; contract Thing {}", encoding="utf-8")

    sources, unresolved = _closure(tmp_path, entry)
    assert unresolved == []
    assert "lib/Thing.sol" in sources

def test_empty_compiler_catalog_is_not_misreported_as_pragma_conflict(monkeypatch):
    monkeypatch.setattr(direct.solcx, "get_installed_solc_versions", lambda: [])
    monkeypatch.setattr(direct.solcx, "get_installable_solc_versions", lambda: [])
    contents = {"A.sol": "pragma solidity ^0.8.20; contract A {}"}

    version, status = direct._compatible_version(contents)

    assert version is None
    assert status == "compiler_unavailable"


def test_compiler_catalog_failure_is_distinguished_from_pragma_conflict(monkeypatch):
    monkeypatch.setattr(direct.solcx, "get_installed_solc_versions", lambda: [])
    def unavailable_catalog():
        raise OSError("catalogue unavailable")
    monkeypatch.setattr(direct.solcx, "get_installable_solc_versions", unavailable_catalog)
    contents = {"A.sol": "pragma solidity ^0.8.20; contract A {}"}

    version, status = direct._compatible_version(contents)

    assert version is None
    assert status == "compiler_version_discovery_failed"
