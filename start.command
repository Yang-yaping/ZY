#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
export ECASH_DATA="${ECASH_DATA:-$PWD/data}"
exec .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
