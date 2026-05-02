#!/usr/bin/env bash
set -euo pipefail

cd /workspace/backend

echo "--- Syncing dependencies ---"
uv sync --extra dev

echo "--- Registering CLI completion ---"
uv run cli --install-completion

echo "--- Initialising workspace ---"
uv run cli init-workspace

echo "--- Done ---"
