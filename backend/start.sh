#!/bin/bash

# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

set -e

echo "🔄 Applying database migrations..."
alembic upgrade head

# Check if schema matches models (for development)
if ! alembic check 2>/dev/null; then
    echo "⚠️  Model changes detected!"
    echo "   Your models have changed but no migration was found."
    echo "   Generating automatic migration..."
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    alembic revision --autogenerate -m "auto_${TIMESTAMP}"
    alembic upgrade head
    
    echo "✅ Migration generated and applied"
    echo "   Note: This migration is temporary and will be lost when the pod restarts."
    echo "   To keep it, copy from alembic/versions/ and commit to your repository."
else
    echo "✅ Database schema is up to date"
fi

echo "🚀 Starting application..."
exec uvicorn app:app --host 0.0.0.0 --port 8000