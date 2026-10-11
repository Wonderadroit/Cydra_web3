from pathlib import Path

from cydra.compiler_state import _source_dependency_closure


def test_source_closure_ignores_commented_out_imports(tmp_path: Path):
    project = tmp_path / "project"
    entry = project / "src" / "chains" / "Mainnet" / "Common.sol"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        'import "../../core/Live.sol";\n'
        '// import "../../core/CurveTricrypto.sol";\n'
        '/* import "@missing/package/Nope.sol"; */\n'
        'contract Common {}\n',
        encoding="utf-8",
    )
    payload = {
        "input": {"sources": {
            "src/chains/Mainnet/Common.sol": {"content": entry.read_text()},
            "src/core/Live.sol": {"content": "contract Live {}"},
            "src/core/CurveTricrypto.sol": {"content": "contract CurveTricrypto {}"},
        }},
        "output": {"sources": {
            "src/chains/Mainnet/Common.sol": {"ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/core/Live.sol": {"ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/core/CurveTricrypto.sol": {"ast": {"nodeType": "SourceUnit", "nodes": []}},
        }},
    }

    allowed, unresolved = _source_dependency_closure(payload, entry, project)

    assert allowed == {"src/chains/Mainnet/Common.sol", "src/core/Live.sol"}
    assert unresolved == ()
