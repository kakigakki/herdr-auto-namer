#!/bin/bash
# Thin wrapper: herdr event -> auto_namer.py
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/auto_namer.py"
