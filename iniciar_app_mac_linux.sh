#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --disable-pip-version-check -q --upgrade pip
python -m pip install --disable-pip-version-check -q -r requirements.txt
python -m streamlit run app.py
