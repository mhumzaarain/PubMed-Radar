#!/bin/sh
set -eu

cd /workspace/backend
/usr/local/bin/uv sync --extra dev

if [ ! -f /workspace/.env ] && [ -f /workspace/.env.example ]; then
    cp /workspace/.env.example /workspace/.env
    echo ".env created from .env.example"
elif [ -f /workspace/.env ]; then
    echo ".env already exists — skipping."
fi
