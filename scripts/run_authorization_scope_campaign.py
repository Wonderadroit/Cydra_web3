from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


EXCLUDED = {"src/facility/IntentDescriptor.sol"}


def _run(command: list[str], *, cwd: Path | None = None, log: Path | None = None) -> int:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(result.stdout, encoding="utf-8")
    else:
        print(result.stdout, end="")
    return result.returncode


def _in_scope_solidity_files(checkout: Path, source_root: Path) -> list[Path]:
    return sorted(
        path for path in source_root.rglob("*.sol")
        if path.is_file() and path.relative_to(checkout).as_posix() not in EXCLUDED
    )


def _stage_flags(payload: dict) -> dict[str, bool]:
    seeds = payload.get("hypothesis_seeds") or []
    hypotheses = payload.get("hypotheses") or []
    has_hypothesis = bool(payload.get("hypothesis")) or bool(hypotheses)
    has_plan = bool(payload.get("experiment")) or bool(payload.get("experiments"))
    has_execution = isinstance(payload.get("blind_execution"), dict)
    return {
        "seeds": bool(seeds),
        "hypothesis": has_hypothesis,
        "experiment_plan": has_plan,
        "execution_attempted": has_execution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the existing authorization runner across every in-scope Solidity file.")
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--target-ref", required=True, help="Full immutable 40-character commit SHA")
    parser.add_argument("--target-path", default="src", help="Source directory to enumerate; defaults to src")
    parser.add_argument("--target-project", default=".")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    per_file_dir = output_dir / "per-file"
    logs_dir = output_dir / "logs"
    per_file_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cydra-scope-enumeration-") as temp:
        checkout = Path(temp) / "target"
        clone = subprocess.run(
            ["git", "clone", "--no-tags", "--recurse-submodules", args.target_repo, str(checkout)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if clone.returncode:
            print(clone.stdout)
            return clone.returncode
        fetched = subprocess.run(
            ["git", "-C", str(checkout), "fetch", "--no-tags", "origin", args.target_ref],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if fetched.returncode:
            print(fetched.stdout)
            return fetched.returncode
        checked = subprocess.run(
            ["git", "-C", str(checkout), "checkout", "--detach", args.target_ref],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if checked.returncode:
            print(checked.stdout)
            return checked.returncode
        resolved = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout.strip()
        if resolved.lower() != args.target_ref.lower():
            raise SystemExit(f"resolved revision mismatch: requested {args.target_ref}, got {resolved}")
        source_root = (checkout / args.target_path).resolve()
        if not source_root.is_dir() or checkout.resolve() not in source_root.parents:
            raise SystemExit(f"target path is not a repository subdirectory: {args.target_path}")
        files = _in_scope_solidity_files(checkout, source_root)
        if not files:
            raise SystemExit(f"no in-scope Solidity files found under {args.target_path}")

        records = []
        runner = Path(__file__).with_name("run_authorization_campaign.py")
        for index, source_file in enumerate(files, start=1):
            relative = source_file.relative_to(checkout).as_posix()
            key = relative.replace("/", "__").replace(".", "_")
            result_path = per_file_dir / f"{key}.json"
            log_path = logs_dir / f"{key}.log"
            command = [
                sys.executable, str(runner),
                "--target-repo", args.target_repo,
                "--target-ref", resolved,
                "--target-path", relative,
                "--target-project", args.target_project,
                "--allow-no-hypothesis",
                "--measurement-only",
                "--output", str(result_path),
            ]
            if args.require_ready:
                command.append("--require-ready")
            return_code = _run(command, log=log_path)
            payload = {}
            if result_path.exists():
                try:
                    payload = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = {}
            stages = _stage_flags(payload)
            records.append({
                "file": relative,
                "result_file": str(result_path.relative_to(output_dir)),
                "log_file": str(log_path.relative_to(output_dir)),
                "runner_exit_code": return_code,
                **stages,
                "classification": payload.get("classification", payload.get("disposition", "NO_RESULT")),
                "finding_gate": payload.get("finding_gate", "NOT_READY"),
            })
            print(f"[{index}/{len(files)}] {relative}: seeds={stages['seeds']} hypothesis={stages['hypothesis']} plan={stages['experiment_plan']} execution={stages['execution_attempted']} exit={return_code}")

    summary = {
        "target_repo": args.target_repo,
        "target_revision": resolved,
        "target_source_path": args.target_path,
        "excluded_paths": sorted(EXCLUDED),
        "solidity_files_enumerated": len(records),
        "files_with_seeds": sum(row["seeds"] for row in records),
        "files_with_seeds_but_no_hypothesis": sum(row["seeds"] and not row["hypothesis"] for row in records),
        "files_with_hypothesis_but_no_experiment_plan": sum(row["hypothesis"] and not row["experiment_plan"] for row in records),
        "files_with_plan_but_no_execution_attempt": sum(row["experiment_plan"] and not row["execution_attempted"] for row in records),
        "files_with_zero_seeds": sum(not row["seeds"] for row in records),
        "files_with_hypothesis": sum(row["hypothesis"] for row in records),
        "files_with_experiment_plan": sum(row["experiment_plan"] for row in records),
        "files_with_execution_attempt": sum(row["execution_attempted"] for row in records),
        "files_with_runner_errors": sum(row["runner_exit_code"] != 0 for row in records),
        "files": records,
        "finding_claim": False,
        "note": "Counts diagnose pipeline transitions; neither missing hypotheses nor successful execution establishes target security or a bounty finding.",
    }
    (output_dir / "campaign-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "files"}, indent=2))
    return 1 if summary["files_with_runner_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
