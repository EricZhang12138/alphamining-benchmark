#!/bin/bash
set -e

# ── env ──────────────────────────────────────────────────────────────────────
export QLIB_DATA_DIR="${QLIB_DATA_DIR:-/data/dev}"
export WORKSPACE_PATH="${WORKSPACE_PATH:-/app/AlphaAgent/git_ignore_folder/RD-Agent_workspace}"
export PICKLE_CACHE_FOLDER_PATH_STR="${PICKLE_CACHE_FOLDER_PATH_STR:-/app/AlphaAgent/pickle_cache}"
export LOOP_N="${LOOP_N:-10}"
export UNIVERSE="${UNIVERSE:-csi500}"
export BACKBONE="${BACKBONE:-deepseek-v3}"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"

mkdir -p "$WORKSPACE_PATH" "$PICKLE_CACHE_FOLDER_PATH_STR" "$OUTPUT_DIR"

# Qlib needs provider_uri to exist; point it at the mounted dev bundle
export QLIB_PROVIDER_URI="$QLIB_DATA_DIR"

echo "[alphaagent] universe=$UNIVERSE backbone=$BACKBONE loop_n=$LOOP_N"
echo "[alphaagent] data=$QLIB_DATA_DIR  workspace=$WORKSPACE_PATH"

# ── run factor mining ────────────────────────────────────────────────────────
conda run -n alphaagent python -m alphaagent.app.qlib_rd_loop.factor_mining \
    --loop_n "$LOOP_N"

# ── convert workspace → candidates.parquet ──────────────────────────────────
conda run -n alphaagent python /app/adapter.py \
    --workspace   "$WORKSPACE_PATH" \
    --output      "$OUTPUT_DIR/candidates.parquet" \
    --system      alphaagent \
    --backbone    "$BACKBONE" \
    --universe    "$UNIVERSE"

echo "[alphaagent] done → $OUTPUT_DIR/candidates.parquet"
