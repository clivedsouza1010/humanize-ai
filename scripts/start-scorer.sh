#!/usr/bin/env bash
# Start the shared scorer unless one is already answering, then wait until it is ready.
set -u
PY="$HOME/.cache/humanize/venv/bin/python"
DETECT="$(cd "$(dirname "$0")" && pwd)/detect.py"
PORT="${HUMANIZE_PORT:-8765}"
LOG="${TMPDIR:-/tmp}/humanize-scorer.log"

# --noproxy, or a configured HTTP proxy would get the request meant for this machine
if reply=$(curl -s --noproxy '*' -X POST -H 'Content-Type: application/json' -d '{"text": "ping"}' "http://127.0.0.1:$PORT/score"); then
  if printf '%s' "$reply" | grep -q '"server": *"humanize"'; then
    echo "scorer already running on 127.0.0.1:$PORT"
    exit 0
  fi
  echo "something else is answering on 127.0.0.1:$PORT; set HUMANIZE_PORT to a free port and run this again" >&2
  exit 1
fi

nohup "$PY" "$DETECT" --serve > "$LOG" 2>&1 &
PID=$!
for _ in $(seq 1 180); do
  if grep -q "scorer ready" "$LOG"; then
    echo "scorer ready on 127.0.0.1:$PORT (pid $PID)"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    cat "$LOG"
    exit 1
  fi
  sleep 1
done
echo "scorer did not start within 3 minutes; see $LOG"
exit 1
