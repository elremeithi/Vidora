#!/bin/sh
# Run Vidora straight from the source folder (after `pip install -r requirements.txt`).
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m vidora "$@"
