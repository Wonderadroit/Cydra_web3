from __future__ import annotations

import argparse
import re
from urllib.parse import urlparse


_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _https_url(value: str, label: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{label} must be an HTTPS URL without embedded credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} must not contain a query string or fragment")
    return value.strip()


def validate_intake(
    program_url: str,
    target_repo: str,
    target_ref: str,
    target_path: str,
    target_project: str = ".",
) -> None:
    """Validate immutable, well-formed campaign intake; does not certify bounty scope."""
    _https_url(program_url, "program_url")
    repo_url = _https_url(target_repo, "target_repo")
    parsed_repo = urlparse(repo_url)
    if parsed_repo.hostname.lower() != "github.com":
        raise ValueError("target_repo must point to github.com")
    segments = [part for part in parsed_repo.path.split("/") if part]
    if len(segments) != 2 or any(part in {".", ".."} for part in segments):
        raise ValueError("target_repo must be a GitHub owner/repository URL")

    if not _SHA_RE.fullmatch(target_ref.strip()):
        raise ValueError("target_ref must be a full 40-character immutable commit SHA")

    for value, label, allow_dot in (
        (target_path, "target_path", False),
        (target_project, "target_project", True),
    ):
        cleaned = value.strip()
        if not cleaned or cleaned.startswith("/") or "\\" in cleaned:
            raise ValueError(f"{label} must be a non-empty relative path")
        parts = cleaned.split("/")
        if any(part in {"", ".."} for part in parts):
            raise ValueError(f"{label} must not contain empty or parent-directory segments")
        if not allow_dot and any(part == "." for part in parts):
            raise ValueError(f"{label} must not contain current-directory segments")
        if allow_dot and cleaned != "." and any(part == "." for part in parts):
            raise ValueError(f"{label} must not contain current-directory segments")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program-url", required=True)
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--target-path", required=True)
    parser.add_argument("--target-project", default=".")
    args = parser.parse_args()
    validate_intake(
        args.program_url, args.target_repo, args.target_ref,
        args.target_path, args.target_project,
    )
    print("INTAKE_VALIDATED_FORMAT_ONLY")
    print("NOTICE: program scope and target/path authorization are not independently verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
