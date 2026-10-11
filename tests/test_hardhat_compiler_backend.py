from pathlib import Path

from cydra.compiler_state import _hardhat_commands, _is_hardhat_project


def test_hardhat_backend_detects_yarn_project_and_uses_locked_install(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (tmp_path / "hardhat.config.js").write_text("module.exports = {};", encoding="utf-8")
    (tmp_path / "yarn.lock").write_text("# yarn lockfile", encoding="utf-8")

    assert _is_hardhat_project(tmp_path)
    install, compile_command = _hardhat_commands(tmp_path)
    assert install[:2] == ("yarn", "install")
    assert "--frozen-lockfile" in install
    assert compile_command == ("yarn", "hardhat", "compile", "--force")


def test_hardhat_backend_uses_npm_ci_when_package_lock_exists(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (tmp_path / "hardhat.config.ts").write_text("export default {};", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    install, compile_command = _hardhat_commands(tmp_path)
    assert install[:2] == ("npm", "ci")
    assert compile_command == ("npx", "--no-install", "hardhat", "compile", "--force")


def test_foundry_project_is_not_misclassified_as_hardhat(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (tmp_path / "hardhat.config.js").write_text("module.exports = {};", encoding="utf-8")
    (tmp_path / "foundry.toml").write_text("[profile.default]", encoding="utf-8")

    assert _is_hardhat_project(tmp_path)
    # Backend selection in compile_state_effects prefers foundry.toml over Hardhat.
