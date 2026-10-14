"""
QuantaAlpha → candidates.parquet adapter.

QuantaAlpha stores per-factor results in:
  <workspace_path>/
    factor_library.json          # metadata for all mined factors
    <factor_id>/
      result.h5                  # factor values (MultiIndex: datetime × instrument)
      factor.py                  # generated implementation

experiment.result is a Qlib backtest metrics pandas Series on the experiment object.
The factor library JSON is the authoritative index; experiment pkl is secondary.
"""

import argparse
import json
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
    except Exception:
        return None


def _read_metrics_from_experiment(exp) -> tuple[float | None, float | None]:
    """Return (mean_rankic, icir) from exp.result Series if available."""
    result = getattr(exp, "result", None)
    if not isinstance(result, (pd.Series, dict)):
        return None, None

    items = result.items() if isinstance(result, pd.Series) else result.items()
    rankic, icir = None, None
    for key, val in items:
        k = str(key).lower()
        if "rank" in k and "ic" in k and "ir" not in k:
            try:
                rankic = float(val)
            except (TypeError, ValueError):
                pass
        if ("ic" in k and "ir" in k) or "icir" in k:
            try:
                icir = float(val)
            except (TypeError, ValueError):
                pass
    return rankic, icir


def extract_candidates(workspace_path: Path) -> pd.DataFrame:
    records = []

    # ── primary path: factor_library.json ───────────────────────────────────
    library_json = workspace_path / "factor_library.json"
    if library_json.exists():
        try:
            library: list[dict] = json.loads(library_json.read_text())
        except Exception:
            library = []

        for entry in library:
            factor_id   = entry.get("factor_id", "")
            factor_name = entry.get("factor_name", factor_id)
            formula     = entry.get("factor_expression", entry.get("formula", ""))
            iteration   = entry.get("iteration", None)
            status      = entry.get("status", "unknown")

            factor_dir = workspace_path / factor_id
            code = ""
            if factor_dir.is_dir() and (factor_dir / "factor.py").exists():
                try:
                    code = (factor_dir / "factor.py").read_text()
                except Exception:
                    pass

            # Try loading experiment pkl for metrics
            exp = _safe_load_pickle(factor_dir / "experiment.pkl") if factor_dir.is_dir() else None
            rankic, icir = _read_metrics_from_experiment(exp) if exp else (None, None)

            records.append({
                "factor_name": factor_name,
                "formula": formula,
                "code": code,
                "dev_rankic": rankic,
                "dev_ic_ir": icir,
                "iteration": iteration,
                "generation_cost_usd": None,
                "valid": status == "success" or bool(code),
                "error": "" if status in ("success", "unknown") else status,
            })

        if records:
            df = pd.DataFrame(records, columns=CANDIDATES_COLUMNS)
            return df

    # ── fallback: walk workspace dirs for experiment.pkl ────────────────────
    for iteration, exp_dir in enumerate(sorted(workspace_path.iterdir())):
        if not exp_dir.is_dir():
            continue

        exp = _safe_load_pickle(exp_dir / "experiment.pkl")
        if exp is None:
            for pkl in exp_dir.glob("*.pkl"):
                exp = _safe_load_pickle(pkl)
                if exp is not None:
                    break

        if exp is not None:
            rankic, icir = _read_metrics_from_experiment(exp)
            sub_workspaces = getattr(exp, "sub_workspace_list", [])
            for idx, ws in enumerate(sub_workspaces):
                task = getattr(ws, "target_task", None)
                factor_name = getattr(task, "factor_name", f"{exp_dir.name}_f{idx}") if task else f"{exp_dir.name}_f{idx}"
                formula = getattr(task, "factor_formulation", "") if task else ""
                ws_path: Path | None = getattr(ws, "workspace_path", None)
                code = ""
                if ws_path and (ws_path / "factor.py").exists():
                    try:
                        code = (ws_path / "factor.py").read_text()
                    except Exception:
                        pass
                records.append({
                    "factor_name": factor_name,
                    "formula": formula,
                    "code": code,
                    "dev_rankic": rankic,
                    "dev_ic_ir": icir,
                    "iteration": iteration,
                    "generation_cost_usd": None,
                    "valid": bool(code),
                    "error": "",
                })
        else:
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
    parser.add_argument("--system",    default="quantaalpha")
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
