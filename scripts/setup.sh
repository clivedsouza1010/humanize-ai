#!/usr/bin/env bash
# One-time install: Python venv in ~/.cache/humanize plus the three models detect.py uses (~6.7 GB).
set -euo pipefail

VENV="$HOME/.cache/humanize/venv"
PYTHON="${PYTHON:-python3}"
# torch, transformers, scikit-learn and pyarrow at these pins need Python 3.11 or newer
too_old() { ! "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; }

if too_old "$PYTHON"; then
  echo "setup needs Python 3.11 or newer, and $PYTHON is $( { command -v "$PYTHON" > /dev/null && "$PYTHON" --version 2>&1; } || echo missing)." >&2
  echo "Run it again with one, for example: PYTHON=python3.11 bash $0" >&2
  exit 1
fi
# a venv left by an older Python or a failed first run is rebuilt, not reused
if [ -e "$VENV" ] && { too_old "$VENV/bin/python" || [ ! -x "$VENV/bin/pip" ]; }; then
  rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/python" ]; then
  mkdir -p "$(dirname "$VENV")"
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q torch==2.15.0 transformers==5.22.1 accelerate==1.15.0 scikit-learn==1.9.1 \
  huggingface_hub==2.4.0 pyarrow==26.0.0 markdown-it-py==4.2.0

"$VENV/bin/python" - <<'EOF'
from huggingface_hub import snapshot_download
# pinned to the same commits as REVISIONS in detect.py, which loads exactly these
for repo, revision in [("Qwen/Qwen2.5-1.5B", "8faed761d45a263340a0528343f099c05c9a4323"),
                       ("Qwen/Qwen2.5-1.5B-Instruct", "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"),
                       ("fakespot-ai/roberta-base-ai-text-detection-v1", "f9cdb14d1f8b105f597d80fa7b56f20c6ea0e9db")]:
    print(snapshot_download(repo, revision=revision, allow_patterns=["*.json", "*.safetensors", "*.txt", "vocab*"]))
EOF
echo "ready: $VENV/bin/python $(dirname "$0")/detect.py <file>"
