#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/runtime/logs"
PID_FILE="$LOG_DIR/jarvis-docker-lab.pid"
LOG_FILE="$LOG_DIR/jarvis-docker-lab.log"

if [[ -f "$PROJECT_ROOT/config/ports.env" ]]; then source "$PROJECT_ROOT/config/ports.env"; fi
if [[ -f "$PROJECT_ROOT/config/ports.local.env" ]]; then source "$PROJECT_ROOT/config/ports.local.env"; fi
if [[ -f "$PROJECT_ROOT/.env" ]]; then source "$PROJECT_ROOT/.env"; fi

FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
FLASK_PORT="${FLASK_PORT:-5103}"
LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
LOCAL_IP="${LOCAL_IP:-127.0.0.1}"

print_status_block(){
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Docker-Lab läuft"
  echo ""
  echo "  Dashboard:  http://${LOCAL_IP}:${FLASK_PORT}/"
  echo "  Link:       http://${LOCAL_IP}:${FLASK_PORT}/link"
  echo "  Info:       http://${LOCAL_IP}:${FLASK_PORT}/info"
  echo "  Health:     http://${LOCAL_IP}:${FLASK_PORT}/health"
  echo ""
  echo "  App-Log:    $LOG_FILE"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

trigger_panel_sync(){
  local health_url="http://127.0.0.1:${FLASK_PORT}/health"
  local sync_url="http://127.0.0.1:${FLASK_PORT}/api/portal/sync"
  local link_url="http://${LOCAL_IP}:${FLASK_PORT}/link"
  local attempt=1 max_attempts=10 health_ok=0
  while [[ "$attempt" -le "$max_attempts" ]]; do
    if curl -fsS --max-time 5 "$health_url" >/dev/null 2>&1; then health_ok=1; break; fi
    sleep 1; attempt=$((attempt+1))
  done
  if [[ "$health_ok" -ne 1 ]]; then
    echo "[Panel]    Auto-Sync übersprungen: Healthcheck nicht erreichbar (${health_url})"
    return 0
  fi
  local tmp code parsed node_sync_ok mcp_ok
  tmp="$(mktemp)"
  code="$(curl -sS -o "$tmp" -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{}' "$sync_url" || true)"
  parsed="$(python3 - "$tmp" <<'PY'
import json,sys
p=sys.argv[1]
try:d=json.load(open(p,'r',encoding='utf-8'))
except Exception:d={}
print('1' if d.get('node_sync_ok') else '0')
print('1' if d.get('mcp_ok') else '0')
PY
)"
  rm -f "$tmp"
  node_sync_ok="$(echo "$parsed" | sed -n '1p')"
  mcp_ok="$(echo "$parsed" | sed -n '2p')"
  if [[ "$code" == "200" && "$node_sync_ok" == "1" && "$mcp_ok" == "1" ]]; then
    echo "[Panel]    Auto-Sync erfolgreich."
  elif [[ "$code" == "502" ]]; then
    echo "[Panel]    Auto-Sync übersprungen: Node noch nicht vollständig verknüpft. Link prüfen: ${link_url}"
  else
    echo "[Panel]    Auto-Sync fehlgeschlagen (HTTP ${code}) ${sync_url}"
  fi
}

mkdir -p "$LOG_DIR"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then python3 -m venv "$VENV_DIR"; fi
source "$VENV_DIR/bin/activate"
echo "Installiere/aktualisiere Requirements ..."
"$PYTHON_BIN" -m pip install -q --upgrade pip
"$PYTHON_BIN" -m pip install -q -r "$PROJECT_ROOT/requirements.txt"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "[Flask]    Bereits aktiv (PID $OLD_PID) — übersprungen"
    print_status_block
    exit 0
  fi
  rm -f "$PID_FILE"
fi

export FLASK_HOST FLASK_PORT
nohup "$PYTHON_BIN" "$PROJECT_ROOT/app.py" >> "$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"
sleep 1
if [[ -z "$PID" ]] || ! kill -0 "$PID" >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "[Flask]    Fehlgeschlagen — siehe Log: $LOG_FILE"
  exit 1
fi

echo "[Flask]    Gestartet (PID $PID)"
trigger_panel_sync || true
print_status_block
