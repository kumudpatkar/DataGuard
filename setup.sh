#!/usr/bin/env bash
set -e
echo "Setting up DataGuard..."
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo
echo "Setup finished. Run ./run.sh to start DataGuard."
