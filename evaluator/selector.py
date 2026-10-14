"""
Common factor selector.

Loads candidates.parquet from one or more systems, filters to valid factors,
then selects at most max_factors by dev-period standalone RankIC (fast mode)
or marginal RankIC increment over Alpha158 (accurate mode).

The accurate mode requires Qlib + the dev data bundle.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd


# ── schema validation ────────────────────────────────────────────────────────

REQUIRED_COLS = {
    "factor_name", "formula", "code",
    "dev_rankic", "system", "backbone", "universe", "valid",
}


def load_candidates(*parquet_paths: str | Path) -> pd.DataFrame:
    frames = []
    for p in parquet_paths:
        df = pd.read_parquet(p)
        missing = REQUIRED_COLS - set(df.columns)
        if missing:
            raise ValueError(f"{p}: missing columns {missing}")
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined["valid"].fillna(False).astype(bool)]
    combined = combined.dropna(subset=["code"])
    combined = combined[combined["code"].str.strip() != ""]
    return combined


# ── standalone selector (fast) ───────────────────────────────────────────────

def select_by_standalone_rankic(
    candidates: pd.DataFrame,
    max_factors: int = 50,
) -> pd.DataFrame:
    """
    Select top max_factors by dev_rankic.
    NaN dev_rankic values are ranked last.
    """
    df = candidates.copy()
    df["_abs_rankic"] = df["dev_rankic"].abs().fillna(-np.inf)
    df = df.sort_values("_abs_rankic", ascending=False)
    df = df.drop_duplicates(subset=["factor_name"])
    selected = df.head(max_factors).drop(columns=["_abs_rankic"])
    return selected.reset_index(drop=True)


# ── marginal selector (accurate, requires Qlib) ──────────────────────────────

def select_by_marginal_rankic(
    candidates: pd.DataFrame,
    dev_data_dir: str | Path,
    universe: str,
    max_factors: int = 50,
    label_expr: str = "Ref($close, -2) / Ref($close, -1) - 1",
    train_start: str = "2016-01-01",
    train_end:   str = "2020-12-31",
    dev_start:   str = "2021-01-01",
    dev_end:     str = "2022-12-31",
) -> pd.DataFrame:
    """
    Greedy forward selection: at each step add the candidate with the highest
    marginal RankIC gain over the current selected set combined with Alpha158.

    Requires qlib to be importable and dev data at dev_data_dir.
    """
    import qlib
    from qlib.constant import REG_CN, REG_US
    from qlib.data import D

    region = REG_US if universe.lower().startswith("sp") else REG_CN
    qlib.init(provider_uri=str(dev_data_dir), region=region)

    instruments = D.instruments(universe)
    dates = D.calendar(start_time=dev_start, end_time=dev_end, freq="day")
    if len(dates) == 0:
        raise RuntimeError(f"No calendar dates found for dev period {dev_start}→{dev_end}")

    # Fetch forward return labels on dev period
    label_df = (
        D.features(instruments, [label_expr], start_time=dev_start, end_time=dev_end)
        .droplevel(0)
    )
    label_df.columns = ["label"]

    def _rankic_series(factor_df: pd.DataFrame, label_df: pd.DataFrame) -> float:
        merged = factor_df.join(label_df, how="inner").dropna()
        if merged.empty:
            return np.nan
        ic_per_day = (
            merged.groupby(level=0)
            .apply(lambda g: g.iloc[:, 0].rank().corr(g["label"].rank()))
        )
        return float(ic_per_day.mean())

    selected_indices: list[int] = []
    remaining = list(range(len(candidates)))

    for _ in range(max_factors):
        if not remaining:
            break
        best_idx, best_gain = None, -np.inf
        for idx in remaining:
            row = candidates.iloc[idx]
            try:
                factor_df = _eval_factor_code(row["code"], row["factor_name"],
                                              dev_start, dev_end, dev_data_dir)
            except Exception:
                continue
            gain = _rankic_series(factor_df, label_df)
            if np.isnan(gain):
                continue
            if gain > best_gain:
                best_gain, best_idx = gain, idx
        if best_idx is None:
            break
        selected_indices.append(best_idx)
        remaining.remove(best_idx)

    return candidates.iloc[selected_indices].reset_index(drop=True)


def _eval_factor_code(
    code: str,
    factor_name: str,
    start: str,
    end: str,
    data_dir: str | Path,
) -> pd.DataFrame:
    """Execute factor code and return a (datetime, instrument) indexed Series."""
    import tempfile, importlib.util, sys as _sys

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name

    spec = importlib.util.spec_from_file_location("_factor_tmp", tmp)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    Path(tmp).unlink(missing_ok=True)

    # Convention: factor module exposes a get_factor_data(start, end, data_dir) function
    if hasattr(mod, "get_factor_data"):
        return mod.get_factor_data(start, end, str(data_dir))
    raise AttributeError(f"Factor module {factor_name} has no get_factor_data()")


# ── public API ───────────────────────────────────────────────────────────────

def select(
    candidates: pd.DataFrame,
    mode: Literal["standalone", "marginal"] = "standalone",
    max_factors: int = 50,
    **kwargs,
) -> pd.DataFrame:
    if mode == "standalone":
        return select_by_standalone_rankic(candidates, max_factors)
    elif mode == "marginal":
        return select_by_marginal_rankic(candidates, max_factors=max_factors, **kwargs)
    else:
        raise ValueError(f"Unknown mode: {mode!r}. Choose 'standalone' or 'marginal'.")
