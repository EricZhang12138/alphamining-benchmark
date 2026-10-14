#!/bin/bash
# Build the AlphaAgent Docker image.
# Run from anywhere; resolves paths relative to this script.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCHMARK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SYSTEM_REPO="${SYSTEM_REPO:-$(cd "$BENCHMARK_ROOT/../../Alphamining_agent_benchmark_cn" && pwd)}"
TAG="${TAG:-alphamining/alphaagent:latest}"

echo "Building $TAG"
echo "  System repo : $SYSTEM_REPO"
echo "  Benchmark   : $BENCHMARK_ROOT"

BUILD_CTX=$(mktemp -d)
trap "rm -rf $BUILD_CTX" EXIT

cp -r "$SYSTEM_REPO/AlphaAgent"          "$BUILD_CTX/AlphaAgent"
cp    "$SCRIPT_DIR/adapter.py"           "$BUILD_CTX/adapter.py"
cp    "$SCRIPT_DIR/entrypoint.sh"        "$BUILD_CTX/entrypoint.sh"

docker build \
    -f "$SCRIPT_DIR/Dockerfile" \
    -t "$TAG" \
    "$BUILD_CTX"

echo "Done: $TAG"
