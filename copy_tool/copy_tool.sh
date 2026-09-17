#!/usr/bin/env bash
# Dev launcher: runs CopyTool from a source checkout using the repo's venv.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PYTHONPATH="$REPO_DIR:$PYTHONPATH"
source "$REPO_DIR/venv/bin/activate"
python "$REPO_DIR/copy_tool/main.py"

echo
echo "Press any key to exit..."
read
