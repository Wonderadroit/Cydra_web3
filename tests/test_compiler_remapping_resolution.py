from pathlib import Path

from cydra.compiler_state import _source_dependency_closure


def test_source_closure_normalizes_relative_keys_and_remappings_without_trailing_slash(tmp_path: Path):
    project = tmp_path / "project"
    entry = project / "src" / "chains" / "Mainnet" / "Intent.sol"
    entry.parent.mkdir(parents=True)
    entry.write_text('import "./Common.sol"; contract Intent {}', encoding="utf-8")
    (project / "remappings.txt").write_text("@permit2/=lib/permit2/src\n", encoding="utf-8")
    payload = {
        "input": {"sources": {
            "src/chains/Mainnet/Intent.sol": {"content": 'import "./Common.sol"; contract Intent {}'},
            "src/chains/Mainnet/Common.sol": {
                "content": 'import "../../core/CurveTricrypto.sol"; import "@permit2/interfaces/ISignatureTransfer.sol";'
            },
            "src/chains/Mainnet/../../core/CurveTricrypto.sol": {"content": "contract CurveTricrypto {}"},
            "lib/permit2/src/interfaces/ISignatureTransfer.sol": {"content": "interface ISignatureTransfer {}"},
            "src/Unrelated.sol": {"content": "contract Unrelated {}"},
        }},
        "output": {"sources": {
            "src/chains/Mainnet/Intent.sol": {"id": 0, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/chains/Mainnet/Common.sol": {"id": 1, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/chains/Mainnet/../../core/CurveTricrypto.sol": {"id": 2, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "lib/permit2/src/interfaces/ISignatureTransfer.sol": {"id": 3, "ast": {"nodeType": "SourceUnit", "nodes": []}},
            "src/Unrelated.sol": {"id": 4, "ast": {"nodeType": "SourceUnit", "nodes": []}},
        }},
    }

    allowed, unresolved = _source_dependency_closure(payload, entry, project)

    assert allowed == {
        "src/chains/Mainnet/Intent.sol",
        "src/chains/Mainnet/Common.sol",
        "src/chains/Mainnet/../../core/CurveTricrypto.sol",
        "lib/permit2/src/interfaces/ISignatureTransfer.sol",
    }
    assert unresolved == ()
