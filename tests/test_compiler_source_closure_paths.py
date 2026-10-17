from pathlib import Path

from cydra.compiler_state import _disk_paths_for_source_keys


def test_disk_paths_for_source_keys_binds_direct_and_remapped_sources(tmp_path: Path) -> None:
    project = tmp_path / "project"
    direct = project / "src" / "Entry.sol"
    remapped = project / "lib" / "vendor" / "Child.sol"
    direct.parent.mkdir(parents=True)
    remapped.parent.mkdir(parents=True)
    direct.write_text("contract Entry {}", encoding="utf-8")
    remapped.write_text("contract Child {}", encoding="utf-8")
    (project / "remappings.txt").write_text("vendor/=lib/vendor/\n", encoding="utf-8")

    closure = dict(_disk_paths_for_source_keys(
        project,
        {"src/Entry.sol", "vendor/Child.sol"},
    ))

    assert Path(closure["src/Entry.sol"]) == direct.resolve()
    assert Path(closure["vendor/Child.sol"]) == remapped.resolve()
