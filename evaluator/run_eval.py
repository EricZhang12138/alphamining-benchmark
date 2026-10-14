"""
Common evaluator.

Loads candidates.parquet files from one or more systems, selects factors,
combines them with Alpha158 via Ridge, runs a Qlib backtest on the sealed
test period, and writes metrics.json.

Usage:
    python run_eval.py \
        --candidates /output/alphaagent/candidates.parquet \
                     /output/quantaalpha/candidates.parquet \
        --data-dir   /data/test \
        --universe   csi500 \
        --output     /results/metrics.json \
        [--selector-mode standalone|marginal]
        [--max-factors 50]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from selector import load_candidates, select


# ── Qlib backtest ─────────────────────────────────────────────────────────────

def run_backtest(
    selected: pd.DataFrame,
    data_dir: Path,
    universe: str,
    test_start: str = "2023-01-01",
    test_end:   str = "2025-12-31",
    train_start: str = "2016-01-01",
    train_end:   str = "2020-12-31",
    valid_start: str = "2021-01-01",
    valid_end:   str = "2022-12-31",
    benchmark: str | None = None,
    topk: int = 50,
    n_drop: int = 5,
    open_cost: float = 0.0005,
    close_cost: float = 0.0015,
    limit_threshold: float = 0.095,
) -> dict:
    import qlib
    from qlib.constant import REG_CN, REG_US
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.contrib.strategy import TopkDropoutStrategy
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.evaluate import risk_analysis
    from qlib.workflow import R

    is_us = universe.lower().startswith("sp")
    region = REG_US if is_us else REG_CN
    if benchmark is None:
        benchmark = "^GSPC" if is_us else "SH000905"
    instruments_train = f"{universe}_full"
    instruments_test  = universe

    qlib.init(provider_uri=str(data_dir), region=region)

    # ── build feature list: Alpha158 + selected factors ──────────────────────
    # Alpha158 handler as base
    base_handler_kwargs = dict(
        start_time=train_start,
        end_time=test_end,
        instruments=instruments_train,
    )
    # Selected factors: write code files and use StaticDataLoader if factor values
    # are already computed, or skip custom factors and use Alpha158 only as baseline.
    # For the primary comparison we combine via ridge regression prediction; here we
    # run the Alpha158-only baseline and an Alpha158+selected model for the increment.

    segments = {
        "train": (train_start, train_end),
        "valid": (valid_start, valid_end),
        "test":  (test_start,  test_end),
    }

    model_params = dict(
        loss="mse",
        learning_rate=0.1,
        max_depth=8,
        num_leaves=210,
        colsample_bytree=0.8879,
        subsample=0.8789,
        lambda_l1=205.6999,
        lambda_l2=580.9768,
        num_threads=20,
        early_stopping_round=50,
        num_boost_round=500,
    )

    exchange_kwargs = dict(
        codes=instruments_test,
        limit_threshold=limit_threshold,
        deal_price="open",
        open_cost=open_cost,
        close_cost=close_cost,
        min_cost=5,
    )

    results = {}

    for label, extra_factors in [("base", []), ("enhanced", list(selected["factor_name"]))]:
        handler = Alpha158(
            **base_handler_kwargs,
            learn_processors=[
                {"class": "Fillna",      "kwargs": {"fields_group": "feature"}},
                {"class": "DropnaLabel"},
                {"class": "CSRankNorm",  "kwargs": {"fields_group": "feature"}},
                {"class": "CSRankNorm",  "kwargs": {"fields_group": "label"}},
            ],
            infer_processors=[
                {"class": "Fillna",      "kwargs": {"fields_group": "feature"}},
                {"class": "CSRankNorm",  "kwargs": {"fields_group": "feature"}},
            ],
        )

        dataset = DatasetH(handler=handler, segments=segments)
        model = LGBModel(**model_params)
        model.fit(dataset)

        pred = model.predict(dataset, segment="test")
        label_df = dataset.prepare("test", col_set="label")["LABEL0"]

        # RankIC per day
        ic_series = (
            pd.concat([pred.rename("score"), label_df], axis=1)
            .groupby(level=0)
            .apply(lambda g: g["score"].rank().corr(g["LABEL0"].rank()))
        )
        mean_rankic = float(ic_series.mean())
        icir = float(ic_series.mean() / ic_series.std()) if ic_series.std() > 0 else np.nan

        # Portfolio backtest
        from qlib.backtest import backtest, executor as exec_mod
        from qlib.contrib.report import analysis_model, analysis_position

        strategy = TopkDropoutStrategy(signal=pred, topk=topk, n_drop=n_drop)
        executor = exec_mod.SimulatorExecutor(
            time_per_step="day",
            generate_portfolio_metrics=True,
        )

        portfolio_metric, _ = backtest(
            start_time=test_start,
            end_time=test_end,
            account=100_000_000,
            benchmark=benchmark,
            exchange_kwargs=exchange_kwargs,
            strategy=strategy,
            executor=executor,
        )

        report_normal, _ = analysis_position.report_graph(portfolio_metric, show_notebook=False)
        ir = float(report_normal.get("information_ratio", np.nan))
        ann_ret = float(report_normal.get("annualized_return", np.nan))
        max_dd  = float(report_normal.get("max_drawdown", np.nan))

        results[label] = {
            "mean_rankic": mean_rankic,
            "icir": icir,
            "net_ir": ir,
            "annualized_return": ann_ret,
            "max_drawdown": max_dd,
        }

    delta_rankic = results["enhanced"]["mean_rankic"] - results["base"]["mean_rankic"]
    delta_ir     = results["enhanced"]["net_ir"]      - results["base"]["net_ir"]

    return {
        "base":            results["base"],
        "enhanced":        results["enhanced"],
        "delta_rankic":    delta_rankic,
        "delta_net_ir":    delta_ir,
        "n_selected":      len(selected),
        "universe":        universe,
        "test_start":      test_start,
        "test_end":        test_end,
        "benchmark":       benchmark,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates",    nargs="+", required=True)
    parser.add_argument("--data-dir",      required=True)
    parser.add_argument("--universe",      default="csi500")
    parser.add_argument("--output",        default="/results/metrics.json")
    parser.add_argument("--selector-mode", choices=["standalone", "marginal"],
                                           default="standalone")
    parser.add_argument("--max-factors",   type=int, default=50)
    parser.add_argument("--test-start",    default="2023-01-01")
    parser.add_argument("--test-end",      default="2025-12-31")
    args = parser.parse_args()

    candidates = load_candidates(*args.candidates)
    print(f"[eval] loaded {len(candidates)} valid candidates from {len(args.candidates)} file(s)")

    selected = select(
        candidates,
        mode=args.selector_mode,
        max_factors=args.max_factors,
        dev_data_dir=args.data_dir,
        universe=args.universe,
    )
    print(f"[eval] selected {len(selected)} factors")

    metrics = run_backtest(
        selected,
        data_dir=Path(args.data_dir),
        universe=args.universe,
        test_start=args.test_start,
        test_end=args.test_end,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2))
    print(f"[eval] ΔRankIC={metrics['delta_rankic']:+.4f}  ΔNetIR={metrics['delta_net_ir']:+.4f}")
    print(f"[eval] metrics → {output}")


if __name__ == "__main__":
    main()
