from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from scripts.run_authorization_campaign import _prepare_isolated_foundry_project

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "staging"


@pytest.mark.parametrize("fixture", sorted(p for p in FIXTURES.iterdir() if p.is_dir()))
def test_staging_fixture_uses_production_closure_and_compiles(tmp_path: Path, fixture: Path):
    started = time.monotonic()
    expected = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    target = tmp_path / "target"
    shutil.copytree(fixture, target)
    source = target / expected["source"]
    destination = tmp_path / "execution-project"

    # Exercise the production staging function directly; do not reimplement traversal.
    _prepare_isolated_foundry_project(target, source, destination)

    staged = {
        p.relative_to(destination).as_posix()
        for p in destination.rglob("*.sol")
        if "test" not in p.relative_to(destination).parts
    }
    missing = set(expected["staged_files"]) - staged
    assert not missing, f"{fixture.name}: missing staged files {sorted(missing)}"

    if fixture.name == "base-emissions-controller":
        # Exact six imports from the historical failure, plus the target source.
        required = {
            "src/protocol/emissions/BaseEmissionsController.sol",
            "src/interfaces/IBaseEmissionsController.sol",
            "src/interfaces/ITrust.sol",
            "src/interfaces/IMetaLayer.sol",
            "src/interfaces/ICoreEmissionsController.sol",
            "src/protocol/emissions/CoreEmissionsController.sol",
            "src/protocol/emissions/MetaERC20Dispatcher.sol",
        }
        assert required <= staged

    forge = shutil.which("forge")
    assert forge, "CI must install Foundry; these fixtures must compile, not only copy files"
    completed = subprocess.run(
        [forge, "build", "--root", str(destination)],
        text=True, capture_output=True, check=False, timeout=25,
    )
    assert completed.returncode == 0, (
        f"{fixture.name} failed forge build\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert time.monotonic() - started < 30, (
        f"{fixture.name} staging+compile exceeded 30 seconds"
    )
