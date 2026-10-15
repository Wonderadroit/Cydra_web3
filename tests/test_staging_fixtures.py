from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from scripts.run_authorization_campaign import _prepare_isolated_foundry_project

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "staging"


def test_seven_historical_staging_layouts_stage_and_compile_under_30_seconds(tmp_path: Path):
    started = time.monotonic()
    forge = shutil.which("forge")
    assert forge, "CI must install Foundry; these fixtures must compile, not only copy files"
    fixtures = sorted(p for p in FIXTURES.iterdir() if p.is_dir())
    assert len(fixtures) == 7, f"expected seven historical layouts, found {len(fixtures)}"

    for fixture in fixtures:
        expected = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
        target = tmp_path / fixture.name / "target"
        destination = tmp_path / fixture.name / "execution-project"
        target.parent.mkdir(parents=True)
        shutil.copytree(fixture, target)
        _prepare_isolated_foundry_project(target, target / expected["source"], destination)

        staged = {
            p.relative_to(destination).as_posix()
            for p in destination.rglob("*.sol")
            if "test" not in p.relative_to(destination).parts
        }
        missing = set(expected["staged_files"]) - staged
        assert not missing, f"{fixture.name}: missing staged files {sorted(missing)}"

        if fixture.name == "base-emissions-controller":
            required = {
                "src/protocol/emissions/BaseEmissionsController.sol",
                "src/interfaces/IBaseEmissionsController.sol",
                "src/interfaces/ITrust.sol",
                "src/interfaces/IMetaLayer.sol",
                "src/interfaces/ICoreEmissionsController.sol",
                "src/protocol/emissions/CoreEmissionsController.sol",
                "src/protocol/emissions/MetaERC20Dispatcher.sol",
            }
            assert required <= staged, f"BaseEmissionsController closure incomplete: {required - staged}"

        completed = subprocess.run(
            [forge, "build", "--root", str(destination)],
            text=True, capture_output=True, check=False, timeout=25,
        )
        assert completed.returncode == 0, (
            f"{fixture.name} failed forge build\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    elapsed = time.monotonic() - started
    assert elapsed < 30, f"seven-fixture staging+compile took {elapsed:.2f}s (budget 30s)"
