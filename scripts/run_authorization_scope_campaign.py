from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
EXCLUDED = {"src/facility/IntentDescriptor.sol"}

def _in_scope_solidity_files(checkout: Path, source_root: Path) -> list[Path]:
    return sorted(p for p in source_root.rglob("*.sol")
                  if p.is_file() and p.relative_to(checkout).as_posix() not in EXCLUDED)

def _stage_flags(payload: dict) -> dict[str, bool]:
    return {
        "seeds": bool(payload.get("hypothesis_seeds")),
        "hypothesis": bool(payload.get("hypothesis") or payload.get("hypotheses")),
        "experiment_plan": bool(payload.get("experiment") or payload.get("experiments")),
        "execution_attempted": isinstance(payload.get("blind_execution"), dict),
    }



def _seed_diagnostics(payload: dict) -> dict:
    """Keep blocked-seed causes visible in the aggregate artifact without reclassifying them."""
    seeds = payload.get("hypothesis_seeds") or payload.get("seeds") or []
    status_counts: dict[str, int] = {}
    blocked_seeds = []
    reason_counts: dict[str, int] = {}
    for seed in seeds:
        if not isinstance(seed, dict):
            continue
        status = str(seed.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "blocked":
            continue
        uncertainty = [str(item) for item in (seed.get("uncertainty") or [])]
        provenance = [str(item) for item in (seed.get("provenance") or [])]
        preconditions = [str(item) for item in (seed.get("preconditions_needed") or [])]
        for reason in uncertainty:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        blocked_seeds.append({
            "seed_id": seed.get("seed_id"),
            "contract": seed.get("target_contract"),
            "function": seed.get("target_function"),
            "source": seed.get("source"),
            "source_line": seed.get("source_line"),
            "invariant_source": seed.get("invariant_source"),
            "observed_writes": list(seed.get("observed_writes") or []),
            "preconditions_needed": preconditions,
            "uncertainty": uncertainty,
            "provenance": provenance,
            "analysis_budget": seed.get("analysis_budget"),
        })
    return {
        "seed_status_counts": status_counts,
        "blocked_seed_count": len(blocked_seeds),
        "blocked_seed_reason_counts": reason_counts,
        "blocked_seeds": blocked_seeds,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--target-ref", required=True, help="Full immutable commit SHA")
    parser.add_argument("--target-path", default="src")
    parser.add_argument("--target-project", default=".")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    (out / "per-file").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cydra-scope-") as tmp:
        repo = Path(tmp) / "target"
        for cmd in (
            ["git", "clone", "--no-tags", "--recurse-submodules", args.target_repo, str(repo)],
            ["git", "-C", str(repo), "fetch", "--no-tags", "origin", args.target_ref],
            ["git", "-C", str(repo), "checkout", "--detach", args.target_ref],
        ):
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        revision = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                  check=True, text=True, capture_output=True).stdout.strip()
        if revision.lower() != args.target_ref.lower():
            raise SystemExit(f"revision mismatch: requested {args.target_ref}, got {revision}")
        root = (repo / args.target_path).resolve()
        if not root.is_dir() or repo.resolve() not in root.parents:
            raise SystemExit(f"invalid source directory: {args.target_path}")
        files = _in_scope_solidity_files(repo, root)
        if not files:
            raise SystemExit(f"no Solidity files found under {args.target_path}")

        records = []
        runner = Path(__file__).with_name("run_authorization_campaign.py")
        for i, source in enumerate(files, 1):
            rel = source.relative_to(repo).as_posix()
            key = rel.replace("/", "__").replace(".", "_")
            result_file, log_file = out / "per-file" / f"{key}.json", out / "logs" / f"{key}.log"
            cmd = [sys.executable, str(runner), "--target-repo", args.target_repo,
                   "--target-ref", revision, "--target-path", rel, "--target-project", args.target_project,
                   "--allow-no-hypothesis", "--measurement-only", "--output", str(result_file)]
            if args.require_ready:
                cmd.append("--require-ready")
            run = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log_file.write_text(run.stdout, encoding="utf-8")
            try:
                payload = json.loads(result_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            stages = _stage_flags(payload)
            seed_diagnostics = _seed_diagnostics(payload)
            records.append({"file": rel, "result": str(result_file.relative_to(out)),
                            "log": str(log_file.relative_to(out)), "exit_code": run.returncode,
                            **stages, **seed_diagnostics,
                            "classification": payload.get("classification", payload.get("disposition", "NO_RESULT")),
                            "finding_gate": payload.get("finding_gate", "NOT_READY")})
            print(f"[{i}/{len(files)}] {rel}: {stages}")

    aggregate_seed_status_counts: dict[str, int] = {}
    aggregate_blocked_reason_counts: dict[str, int] = {}
    for record in records:
        for status, count in record.get("seed_status_counts", {}).items():
            aggregate_seed_status_counts[status] = aggregate_seed_status_counts.get(status, 0) + count
        for reason, count in record.get("blocked_seed_reason_counts", {}).items():
            aggregate_blocked_reason_counts[reason] = aggregate_blocked_reason_counts.get(reason, 0) + count

    summary = {
        "target_repo": args.target_repo, "target_revision": revision, "target_source_path": args.target_path,
        "seed_status_counts": aggregate_seed_status_counts,
        "blocked_seed_count": sum(r.get("blocked_seed_count", 0) for r in records),
        "blocked_seed_reason_counts": aggregate_blocked_reason_counts,
        "excluded_paths": sorted(EXCLUDED), "solidity_files_enumerated": len(records),
        "files_with_zero_seeds": sum(not r["seeds"] for r in records),
        "files_with_seeds": sum(r["seeds"] for r in records),
        "files_with_seeds_but_no_hypothesis": sum(r["seeds"] and not r["hypothesis"] for r in records),
        "files_with_hypothesis": sum(r["hypothesis"] for r in records),
        "files_with_hypothesis_but_no_experiment_plan": sum(r["hypothesis"] and not r["experiment_plan"] for r in records),
        "files_with_experiment_plan": sum(r["experiment_plan"] for r in records),
        "files_with_plan_but_no_execution_attempt": sum(r["experiment_plan"] and not r["execution_attempted"] for r in records),
        "files_with_execution_attempt": sum(r["execution_attempted"] for r in records),
        "files_with_runner_errors": sum(r["exit_code"] != 0 for r in records),
        "files": records, "finding_claim": False,
    }
    (out / "campaign-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "files"}, indent=2))
    return int(summary["files_with_runner_errors"] > 0)

if __name__ == "__main__":
    raise SystemExit(main())
