from pathlib import Path

from scripts.run_authorization_campaign import _prepare_isolated_foundry_project


def test_isolated_project_preserves_rooted_vendored_imports(tmp_path: Path) -> None:
    target = tmp_path / "target"
    source = target / "src" / "TransferGuardFactory.sol"
    solady = target / "lib" / "solady" / "src" / "utils" / "LibClone.sol"
    forge_std = target / "lib" / "forge-std" / "src" / "Test.sol"
    source.parent.mkdir(parents=True)
    solady.parent.mkdir(parents=True)
    forge_std.parent.mkdir(parents=True)
    source.write_text(
        'pragma solidity ^0.8.20;\n'
        'import {LibClone} from "lib/solady/src/utils/LibClone.sol";\n'
        'import {Test} from "forge-std/Test.sol";\n'
        'contract TransferGuardFactory {}\n',
        encoding="utf-8",
    )
    solady.write_text("pragma solidity ^0.8.20; library LibClone {}\n", encoding="utf-8")
    forge_std.write_text("pragma solidity ^0.8.20; contract Test {}\n", encoding="utf-8")
    (target / "remappings.txt").write_text(
        "forge-std/=lib/forge-std/src/\n", encoding="utf-8"
    )

    isolated = tmp_path / "isolated"
    _prepare_isolated_foundry_project(target, source, isolated)

    assert (isolated / "src" / "TransferGuardFactory.sol").is_file()
    assert (isolated / "lib" / "solady" / "src" / "utils" / "LibClone.sol").is_file()
    assert (isolated / "lib" / "forge-std" / "src" / "Test.sol").is_file()
    remappings = (isolated / "remappings.txt").read_text(encoding="utf-8")
    assert "forge-std/=lib/forge-std/src/" in remappings
