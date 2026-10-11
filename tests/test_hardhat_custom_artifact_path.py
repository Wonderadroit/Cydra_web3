from pathlib import Path

from cydra.compiler_state import _hardhat_build_info_root


def test_hardhat_build_info_root_honors_custom_artifact_directory(tmp_path: Path):
    (tmp_path / "hardhat.config.ts").write_text(
        'export default { paths: { artifacts: "build/artifacts" } };',
        encoding="utf-8",
    )

    assert _hardhat_build_info_root(tmp_path) == tmp_path / "build" / "artifacts" / "build-info"


def test_hardhat_build_info_root_defaults_to_artifacts(tmp_path: Path):
    (tmp_path / "hardhat.config.js").write_text("module.exports = {};", encoding="utf-8")

    assert _hardhat_build_info_root(tmp_path) == tmp_path / "artifacts" / "build-info"
