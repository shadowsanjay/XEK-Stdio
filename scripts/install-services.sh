#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[setup,test,transcription]'
if [ ! -f .env ]; then .venv/bin/python scripts/configure_local.py; fi
.venv/bin/python scripts/doctor.py
printf '%s\n' 'Install Ollama from its official OS instructions, FFmpeg with your package manager, and follow models/INSTALL.md.'
printf '%s\n' 'No large AI weights have been downloaded. Model scripts check hardware and authorization first.'
