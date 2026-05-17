#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/runtime/logs/jarvis-docker-lab.pid"
if [[ ! -f "$PID_FILE" ]]; then echo "Status: stopped"; exit 0; fi
PID="$(cat "$PID_FILE")"
if kill -0 "$PID" >/dev/null 2>&1; then echo "Status: running (PID=$PID)"; else rm -f "$PID_FILE"; echo "Status: stale-pid (PID=$PID)"; fi
