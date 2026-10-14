"""
AlphaAgent → candidates.parquet adapter.

Walks the RD-Agent workspace, loads pickled QlibFactorExperiment objects,
and extracts per-factor metadata + dev-period IC metrics.

Workspace layout (per run):
  <workspace_path>/
    <exp_id>/
      <task_id>/
        result.h5          # factor values (datetime × instrument)
        factor.py          # generated implementation
      experiment.pkl       # serialised QlibFactorExperiment (has .result Series)
"""

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd
import numpy as np

CANDIDATES_COLUMNS = [
    "factor_name", "formula", "code",
    "dev_rankic", "dev_ic_ir",
    "iteration", "generation_cost_usd",
    "system", "backbone", "universe",
    "valid", "error",
]


def _safe_load_pickle(path: Path):
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        return None


def _extract_from_experiment(exp) -> list[dict]:
    """Pull one record per sub-task from a QlibFactorExperiment."""
    records = []
    sub_workspaces = getattr(exp, "sub_workspace_list", [])
    exp_result: pd.Series | None = getattr(exp, "result", None)

    # exp.result is a Qlib backtest metrics Series; extract portfolio IC if present
    portfolio_ic = None
    portfolio_icir = None
    if isinstance(exp_result, pd.Series):
        for key in exp_result.index:
            k = str(key).lower()
            if "mean" in k and "ic" in k and "ir" not in k:
                portfolio_ic = float(exp_result[key])
            if "ir" in k and "ic" in k:
                portfolio_icir = float(exp_result[key])

    for idx, ws in enumerate(sub_workspaces):
        task = getattr(ws, "target_task", None)
        if task is None:
            continue

        factor_name = getattr(task, "factor_name", f"factor_{idx}")
        formula = getattr(task, "factor_formulation", "")
        description = getattr(task, "factor_description", "")

        # Try to read generated code from workspace
        code = ""
        ws_path: Path | None = getattr(ws, "workspace_path", None)
        if ws_path and (ws_path / "factor.py").exists():
            try:
                code = (ws_path / "factor.py").read_text()
            except Exception:
                pass

        # Per-factor IC: compute from result.h5 vs forward returns if available
        dev_rankic = _compute_ic_from_h5(ws_path) if ws_path else None
        # Fall back to portfolio-level IC when per-factor not computable
        if dev_rankic is None:
            dev_rankic = portfolio_ic

        records.append({
            "factor_name": factor_name,
            "formula": formula,
            "code": code,
            "dev_rankic": dev_rankic,
            "dev_ic_ir": portfolio_icir,
            "iteration": None,   # filled later by caller
            "generation_cost_usd": None,
            "valid": code != "" or dev_rankic is not None,
            "error": "",
        })

    return records


def _compute_ic_from_h5(ws_path: Path) -> float | None:
    """Compute cross-sectional rank IC from result.h5 factor values if present."""
    h5 = ws_path / "result.h5"
    if not h5.exists():
        return None
    try:
        factor_vals: pd.DataFrame = pd.read_hdf(str(h5))
        # factor_vals is a MultiIndex (datetime, instrument) Series or DataFrame
        if isinstance(factor_vals, pd.DataFrame):
            factor_vals = factor_vals.iloc[:, 0]
        # Simple cross-sectional rank correlation with next-day return would require
        # access to price data here; return NaN as a sentinel so the evaluator
        # can recompute it from /data/dev during selection.
        return float("nan")
    except Exception:
        return None


def extract_candidates(workspace_path: Path) -> pd.DataFrame:
    records = []

    # Each direct subdirectory of workspace_path is one experiment round
    for iteration, exp_dir in enumerate(sorted(workspace_path.iterdir())):
        if not exp_dir.is_dir():
            continue

        exp = _safe_load_pickle(exp_dir / "experiment.pkl")
        if exp is None:
            # Try any pkl file in the dir
            for pkl in exp_dir.glob("*.pkl"):
                exp = _safe_load_pickle(pkl)
                if exp is not None:
                    break

        if exp is not None:
            for rec in _extract_from_experiment(exp):
                rec["iteration"] = iteration
                records.append(rec)
            continue

        # No experiment pkl — fall back: scan factor.py files directly
        for factor_py in exp_dir.rglob("factor.py"):
            try:
                code = factor_py.read_text()
            except Exception:
                code = ""
            records.append({
                "factor_name": factor_py.parent.name,
                "formula": "",
                "code": code,
                "dev_rankic": None,
                "dev_ic_ir": None,
                "iteration": iteration,
                "generation_cost_usd": None,
                "valid": bool(code),
                "error": "experiment.pkl not found",
            })

    return pd.DataFrame(records, columns=CANDIDATES_COLUMNS) if records \
        else pd.DataFrame(columns=CANDIDATES_COLUMNS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output",    required=True)
    parser.add_argument("--system",    default="alphaagent")
    parser.add_argument("--backbone",  default="unknown")
    parser.add_argument("--universe",  default="csi500")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    if not workspace.exists():
        print(f"[adapter] workspace not found: {workspace}", file=sys.stderr)
        sys.exit(1)

    df = extract_candidates(workspace)
    df["system"]   = args.system
    df["backbone"] = args.backbone
    df["universe"] = args.universe

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)
    print(f"[adapter] wrote {len(df)} candidates → {output}")


if __name__ == "__main__":
    main()
