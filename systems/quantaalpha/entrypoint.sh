#!/bin/bash
set -e

# ── env ──────────────────────────────────────────────────────────────────────
export QLIB_DATA_DIR="${QLIB_DATA_DIR:-/data/dev}"
export DATA_RESULTS_DIR="${DATA_RESULTS_DIR:-/app/QuantaAlpha/data/results}"
export EXPERIMENT_ID="${EXPERIMENT_ID:-exp_$(date +%Y%m%d_%H%M%S)}"
export WORKSPACE_PATH="${DATA_RESULTS_DIR}/workspace_${EXPERIMENT_ID}"
export PICKLE_CACHE_FOLDER_PATH_STR="${DATA_RESULTS_DIR}/pickle_cache_${EXPERIMENT_ID}"
export LOOP_N="${LOOP_N:-10}"
export UNIVERSE="${UNIVERSE:-csi500}"
export BACKBONE="${BACKBONE:-deepseek-v3}"
export DIRECTION="${DIRECTION:-price-volume factor mining}"
OUTPUT_DIR="${OUTPUT_DIR:-/output}"

mkdir -p "$WORKSPACE_PATH" "$PICKLE_CACHE_FOLDER_PATH_STR" "$OUTPUT_DIR"

echo "[quantaalpha] universe=$UNIVERSE backbone=$BACKBONE loop_n=$LOOP_N"
echo "[quantaalpha] data=$QLIB_DATA_DIR  workspace=$WORKSPACE_PATH"

# ── run factor mining ────────────────────────────────────────────────────────
conda run -n quantaalpha quantaalpha mine \
    --direction "$DIRECTION" \
    --step_n    "$LOOP_N" \
    --config_path configs/experiment.yaml

# ── convert workspace → candidates.parquet ──────────────────────────────────
conda run -n quantaalpha python /app/adapter.py \
    --workspace   "$WORKSPACE_PATH" \
    --output      "$OUTPUT_DIR/candidates.parquet" \
    --system      quantaalpha \
    --backbone    "$BACKBONE" \
    --universe    "$UNIVERSE"

echo "[quantaalpha] done → $OUTPUT_DIR/candidates.parquet"
