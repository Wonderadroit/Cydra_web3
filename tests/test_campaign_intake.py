import pytest

from scripts.validate_campaign_intake import validate_intake


VALID = {
    "program_url": "https://immunefi.com/bug-bounty/example/scope/",
    "target_repo": "https://github.com/example/contracts",
    "target_ref": "0123456789abcdef0123456789abcdef01234567",
    "target_path": "src/Target.sol",
    "target_project": ".",
}


def test_accepts_well_formed_pinned_intake():
    validate_intake(**VALID)


@pytest.mark.parametrize("target_ref", ["main", "v1.2.3", "deadbeef", ""])
def test_rejects_mutable_or_short_target_refs(target_ref):
    with pytest.raises(ValueError, match="40-character"):
        validate_intake(**{**VALID, "target_ref": target_ref})


@pytest.mark.parametrize("target_path", ["/etc/passwd", "../Target.sol", "src/../Target.sol", ""])
def test_rejects_unsafe_source_paths(target_path):
    with pytest.raises(ValueError):
        validate_intake(**{**VALID, "target_path": target_path})


@pytest.mark.parametrize("target_repo", [
    "http://github.com/example/contracts",
    "https://github.com/example/contracts?ref=main",
    "https://example.com/example/contracts",
    "https://user:password@github.com/example/contracts",
    "https://github.com/example",
])
def test_rejects_noncanonical_repository_urls(target_repo):
    with pytest.raises(ValueError):
        validate_intake(**{**VALID, "target_repo": target_repo})


def test_rejects_non_https_program_url():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_intake(**{**VALID, "program_url": "http://immunefi.com/bug-bounty/example/scope/"})


def test_root_project_path_is_allowed_but_parent_traversal_is_not():
    validate_intake(**VALID, target_project=".")
    with pytest.raises(ValueError):
        validate_intake(**{**VALID, "target_project": "../"})
