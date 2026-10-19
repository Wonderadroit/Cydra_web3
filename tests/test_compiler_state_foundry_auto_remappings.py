from pathlib import Path

from cydra.compiler_state import _project_remappings, _source_dependency_closure


def test_compiler_closure_infers_openzeppelin_foundry_library_without_explicit_remappings(
    tmp_path: Path,
) -> None:
    project = tmp_path
    entry = project / "src" / "Vault.sol"
    dependency = (
        project / "lib" / "openzeppelin-contracts" / "contracts" / "access" / "Ownable.sol"
    )
    entry.parent.mkdir(parents=True)
    dependency.parent.mkdir(parents=True)
    entry.write_text(
        'pragma solidity ^0.8.20; import "@openzeppelin/contracts/access/Ownable.sol";',
        encoding="utf-8",
    )
    dependency.write_text("pragma solidity ^0.8.20; contract Ownable {}", encoding="utf-8")
    (project / "foundry.toml").write_text(
        '[profile.default]\nsrc = "src"\nlibs = ["lib"]\n', encoding="utf-8"
    )

    mappings = _project_remappings(project)
    assert (
        "@openzeppelin/contracts/",
        "lib/openzeppelin-contracts/contracts/",
    ) in mappings

    source_key = "src/Vault.sol"
    dependency_key = "lib/openzeppelin-contracts/contracts/access/Ownable.sol"
    payload = {
        "input": {
            "sources": {
                source_key: {"content": entry.read_text(encoding="utf-8")},
                dependency_key: {"content": dependency.read_text(encoding="utf-8")},
            }
        },
        "output": {
            "sources": {
                source_key: {"id": 0},
                dependency_key: {"id": 1},
            }
        },
    }

    closure, unresolved = _source_dependency_closure(payload, entry, project)
    assert closure == {source_key, dependency_key}
    assert unresolved == ()
