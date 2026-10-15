from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.run_authorization_campaign import _prepare_isolated_foundry_project


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.parametrize(
    ("layout", "remappings", "imports", "dependencies", "expected_paths"),
    [
        (
            "local-lib-submodule",
            "forge-std/=lib/forge-std/src/\n",
            'import "forge-std/Test.sol";',
            {
                "lib/forge-std/src/Test.sol":
                    "pragma solidity ^0.8.20; library Test { function value() internal pure returns (uint256) { return 1; } }",
            },
            ["src/lib/forge-std/src/Test.sol"],
        ),
        (
            "nested-lib-relative-imports",
            "nested/=lib/nested/src/\n",
            'import "nested/Child.sol";',
            {
                "lib/nested/src/Child.sol":
                    'pragma solidity ^0.8.20; import "./Base.sol"; contract Child is Base {}',
                "lib/nested/src/Base.sol":
                    "pragma solidity ^0.8.20; contract Base { function value() public pure returns (uint256) { return 2; } }",
            },
            ["src/lib/nested/src/Child.sol", "src/lib/nested/src/Base.sol"],
        ),
        (
            "npm-package",
            "@openzeppelin/=node_modules/@openzeppelin/\n",
            'import "@openzeppelin/contracts/access/AccessControl.sol";',
            {
                "node_modules/@openzeppelin/contracts/access/AccessControl.sol":
                    "pragma solidity ^0.8.20; contract AccessControl {}",
            },
            ["node_modules/@openzeppelin/contracts/access/AccessControl.sol"],
        ),
        (
            "mixed-npm-and-lib",
            "forge-std/=lib/forge-std/src/\n@openzeppelin/=node_modules/@openzeppelin/\n",
            'import "forge-std/Test.sol"; import "@openzeppelin/contracts/access/AccessControl.sol";',
            {
                "lib/forge-std/src/Test.sol":
                    "pragma solidity ^0.8.20; library Test { function value() internal pure returns (uint256) { return 3; } }",
                "node_modules/@openzeppelin/contracts/access/AccessControl.sol":
                    "pragma solidity ^0.8.20; contract AccessControl {}",
            },
            [
                "src/lib/forge-std/src/Test.sol",
                "node_modules/@openzeppelin/contracts/access/AccessControl.sol",
            ],
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_isolated_foundry_staging_supports_dependency_layouts(
    tmp_path: Path,
    layout: str,
    remappings: str,
    imports: str,
    dependencies: dict[str, str],
    expected_paths: list[str],
) -> None:
    target = tmp_path / layout
    source = target / "src" / "Entry.sol"
    _write(
        source,
        "pragma solidity ^0.8.20; "
        + imports
        + " contract Entry { function value() external pure returns (uint256) { return 1; } }",
    )
    _write(target / "remappings.txt", remappings)
    for relative, content in dependencies.items():
        _write(target / relative, content)

    isolated = tmp_path / f"{layout}-isolated"
    _prepare_isolated_foundry_project(target, source, isolated)

    for relative in expected_paths:
        assert (isolated / relative).is_file(), f"{layout}: missing staged dependency {relative}"

    foundry_config = (isolated / "foundry.toml").read_text(encoding="utf-8")
    assert "node_modules/node_modules/" not in foundry_config
    if "node_modules/@openzeppelin/" in remappings:
        assert "@openzeppelin/=node_modules/@openzeppelin/" in foundry_config
        assert "@openzeppelin/=node_modules/node_modules/" not in foundry_config

    # CI installs Foundry for the regression job. Keep this test runnable in
    # lightweight local Python environments while making CI prove compilation.
    if shutil.which("forge"):
        completed = subprocess.run(
            ["forge", "build"],
            cwd=isolated,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, (
            f"{layout} isolated project failed forge build\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
