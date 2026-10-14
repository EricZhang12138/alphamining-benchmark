"""
Experiment orchestrator.

Launches one Docker container per (system, run) pair, collects candidates.parquet
outputs, then calls the evaluator.

Usage:
    python run_experiment.py \
        --systems alphaagent quantaalpha \
        --universe csi500 \
        --backbone deepseek-v3 \
        --runs 5 \
        --loop-n 10 \
        --dev-data-dir  /path/to/dev_bundle \
        --test-data-dir /path/to/test_bundle \
        --output-dir    ./experiment_results/exp_001
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SYSTEM_IMAGES = {
    "alphaagent":  "alphamining/alphaagent:latest",
    "quantaalpha": "alphamining/quantaalpha:latest",
}


def docker_run(
    image: str,
    dev_data_dir: Path,
    output_dir: Path,
    env: dict[str, str],
    run_id: str,
) -> subprocess.CompletedProcess:
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{dev_data_dir.resolve()}:/data/dev:ro",
        "-v", f"{output_dir.resolve()}:/output",
    ]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd.append(image)

    print(f"[{run_id}] launching {image}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    return result


def collect_candidates(output_dir: Path) -> list[Path]:
    return sorted(output_dir.rglob("candidates.parquet"))


def run_evaluator(
    candidates_paths: list[Path],
    test_data_dir: Path,
    universe: str,
    output_path: Path,
    selector_mode: str = "standalone",
    max_factors: int = 50,
) -> dict:
    evaluator_script = Path(__file__).parent.parent / "evaluator" / "run_eval.py"
    cmd = [
        sys.executable, str(evaluator_script),
        "--candidates", *[str(p) for p in candidates_paths],
        "--data-dir",   str(test_data_dir),
        "--universe",   universe,
        "--output",     str(output_path),
        "--selector-mode", selector_mode,
        "--max-factors",   str(max_factors),
    ]
    subprocess.run(cmd, check=True)
    if output_path.exists():
        return json.loads(output_path.read_text())
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--systems",        nargs="+", required=True,
                        choices=list(SYSTEM_IMAGES))
    parser.add_argument("--universe",       default="csi500")
    parser.add_argument("--backbone",       default="deepseek-v3")
    parser.add_argument("--runs",           type=int, default=1)
    parser.add_argument("--loop-n",         type=int, default=10,
                        help="Number of mining iterations per run")
    parser.add_argument("--dev-data-dir",   required=True)
    parser.add_argument("--test-data-dir",  required=True)
    parser.add_argument("--output-dir",     required=True)
    parser.add_argument("--selector-mode",  default="standalone",
                        choices=["standalone", "marginal"])
    parser.add_argument("--max-factors",    type=int, default=50)
    parser.add_argument("--llm-api-base",   default=os.environ.get("LLM_API_BASE", ""))
    parser.add_argument("--llm-api-key",    default=os.environ.get("LLM_API_KEY",  ""))
    parser.add_argument("--budget-usd",     type=float, default=100.0)
    args = parser.parse_args()

    dev_data  = Path(args.dev_data_dir).resolve()
    test_data = Path(args.test_data_dir).resolve()
    out_root  = Path(args.output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    experiment_meta = {
        "systems":   args.systems,
        "universe":  args.universe,
        "backbone":  args.backbone,
        "runs":      args.runs,
        "loop_n":    args.loop_n,
        "timestamp": datetime.utcnow().isoformat(),
    }
    (out_root / "experiment.json").write_text(json.dumps(experiment_meta, indent=2))

    all_candidates: list[Path] = []
    failed_runs: list[str] = []

    for system in args.systems:
        image = SYSTEM_IMAGES[system]
        for run_idx in range(args.runs):
            run_id  = f"{system}_run{run_idx:02d}"
            run_dir = out_root / system / f"run{run_idx:02d}"
            run_dir.mkdir(parents=True, exist_ok=True)

            env = {
                "UNIVERSE":        args.universe,
                "BACKBONE":        args.backbone,
                "LOOP_N":          str(args.loop_n),
                "BUDGET_USD":      str(args.budget_usd),
                "LLM_API_BASE":    args.llm_api_base,
                "LLM_API_KEY":     args.llm_api_key,
                "EXPERIMENT_ID":   run_id,
                "OUTPUT_DIR":      "/output",
            }

            result = docker_run(image, dev_data, run_dir, env, run_id)

            candidates_file = run_dir / "candidates.parquet"
            if result.returncode != 0 or not candidates_file.exists():
                print(f"[orchestrator] FAILED: {run_id} (exit {result.returncode})")
                failed_runs.append(run_id)
            else:
                all_candidates.append(candidates_file)
                print(f"[orchestrator] OK: {run_id} → {candidates_file}")

    if not all_candidates:
        print("[orchestrator] no candidates collected; aborting evaluation")
        sys.exit(1)

    print(f"\n[orchestrator] collected {len(all_candidates)} candidate files; running evaluator")

    metrics = run_evaluator(
        all_candidates,
        test_data,
        args.universe,
        out_root / "metrics.json",
        selector_mode=args.selector_mode,
        max_factors=args.max_factors,
    )

    summary = {
        "experiment": experiment_meta,
        "runs_ok":     len(all_candidates),
        "runs_failed": len(failed_runs),
        "failed":      failed_runs,
        "metrics":     metrics,
    }
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n[orchestrator] done")
    if metrics:
        print(f"  ΔRankIC  = {metrics.get('delta_rankic', 'n/a'):+.4f}")
        print(f"  ΔNet IR  = {metrics.get('delta_net_ir',  'n/a'):+.4f}")
    print(f"  results  → {out_root}")


if __name__ == "__main__":
    main()
