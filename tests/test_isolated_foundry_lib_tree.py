from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.run_authorization_campaign import _prepare_isolated_foundry_project


@pytest.mark.parametrize("with_remappings", [False, True], ids=["no-remappings", "remappings-present"])
def test_isolated_project_compiles_with_complete_lib_tree(tmp_path: Path, with_remappings: bool):
    forge = shutil.which("forge")
    if forge is None:
        pytest.skip("Foundry is installed in the campaign CI environment")

    target = tmp_path / "target"
    source = target / "src" / "Probe.sol"
    library = target / "lib" / "solady" / "src" / "auth" / "OwnableRoles.sol"
    source.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    source.write_text(
        'pragma solidity ^0.8.20;\n'
        'import "lib/solady/src/auth/OwnableRoles.sol";\n'
        'contract Probe is OwnableRoles {}\n',
        encoding="utf-8",
    )
    library.write_text(
        'pragma solidity ^0.8.20;\n'
        'contract OwnableRoles {}\n',
        encoding="utf-8",
    )
    if with_remappings:
        (target / "remappings.txt").write_text(
            "solady/=lib/solady/src/\n",
            encoding="utf-8",
        )

    isolated = tmp_path / "isolated"
    _prepare_isolated_foundry_project(target, source, isolated)

    staged_library = isolated / "lib" / "solady" / "src" / "auth" / "OwnableRoles.sol"
    assert staged_library.is_file()
    result = subprocess.run(
        [forge, "build"],
        cwd=isolated,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
