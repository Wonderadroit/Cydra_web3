import json
from pathlib import Path

from cydra.compiler_state import _source_dependency_closure


def test_source_dependency_closure_excludes_unrelated_compilation_sources(tmp_path: Path):
    project = tmp_path / "project"
    entry = project / "src" / "Entry.sol"
    entry.parent.mkdir(parents=True)
    entry.write_text('import "./Base.sol"; contract Entry is Base {}', encoding="utf-8")
    (project / "src" / "Base.sol").write_text("contract Base { uint public value; }", encoding="utf-8")
    (project / "src" / "Other.sol").write_text("contract Other { uint public unrelated; }", encoding="utf-8")
    payload = {
        "input": {"sources": {
            "src/Entry.sol": {"content": 'import "./Base.sol"; contract Entry is Base {}'},
            "src/Base.sol": {"content": "contract Base { uint public value; }"},
            "src/Other.sol": {"content": "contract Other { uint public unrelated; }"},
        }},
        "output": {"sources": {
            "src/Entry.sol": {"id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/Base.sol": {"id": 1, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/Other.sol": {"id": 2, "ast": {"nodeType": "SourceUnit", "nodes": []}},
        }},
    }

    allowed, unresolved = _source_dependency_closure(payload, entry, project)

    assert allowed == {"src/Entry.sol", "src/Base.sol"}
    assert unresolved == ()


def test_source_dependency_closure_resolves_bare_node_modules_import(tmp_path: Path):
    project = tmp_path / "project"
    entry = project / "src" / "Entry.sol"
    entry.parent.mkdir(parents=True)
    entry.write_text('import "@sample/pkg/Thing.sol"; contract Entry {}', encoding="utf-8")
    package = project / "node_modules" / "@sample" / "pkg" / "Thing.sol"
    package.parent.mkdir(parents=True)
    package.write_text("contract Thing {}", encoding="utf-8")
    payload = {
        "input": {"sources": {
            "src/Entry.sol": {"content": 'import "@sample/pkg/Thing.sol"; contract Entry {}'},
            "node_modules/@sample/pkg/Thing.sol": {"content": "contract Thing {}"},
            "src/Other.sol": {"content": "contract Other {}"},
        }},
        "output": {"sources": {
            "src/Entry.sol": {"id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "node_modules/@sample/pkg/Thing.sol": {"id": 1, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/Other.sol": {"id": 2, "ast": {"nodeType": "SourceUnit", "nodes": []}},
        }},
    }

    allowed, unresolved = _source_dependency_closure(payload, entry, project)

    assert allowed == {"src/Entry.sol", "node_modules/@sample/pkg/Thing.sol"}
    assert unresolved == ()
