#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/runtime/logs/jarvis-docker-lab.pid"
if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then kill "$pid" || true; sleep 1; fi
  rm -f "$PID_FILE"
fi
for pid in $(pgrep -f "Joormann-Media-Jarvis-Docker-Lab/app.py" || true); do
  kill "$pid" 2>/dev/null || true
 done
