#!/bin/sh
set -eu

python -c 'from stockwise.config import load_settings; load_settings()'
python -m alembic upgrade head
exec python -m uvicorn stockwise.api:app --host 0.0.0.0 --port "${PORT:-8000}"
