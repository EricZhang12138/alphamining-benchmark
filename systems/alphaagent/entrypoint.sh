#!/bin/bash
set -e

# ── env ──────────────────────────────────────────────────────────────────────
# Map orchestrator-injected vars to what AlphaAgent reads
export OPENAI_API_KEY="${LLM_API_KEY:-${OPENAI_API_KEY:-}}"
export OPENAI_BASE_URL="${LLM_API_BASE:-${OPENAI_BASE_URL:-https://api.openai.com/v1}}"
export CHAT_MODEL="${BACKBONE:-gpt-5.2}"
export REASONING_MODEL="${BACKBONE:-gpt-5.2}"

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
