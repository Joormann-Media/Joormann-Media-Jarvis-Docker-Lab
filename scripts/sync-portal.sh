#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT_DIR/config/ports.env" ]]; then source "$ROOT_DIR/config/ports.env"; fi
if [[ -f "$ROOT_DIR/config/ports.local.env" ]]; then source "$ROOT_DIR/config/ports.local.env"; fi
PORT="${FLASK_PORT:-5103}"
curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' "http://127.0.0.1:${PORT}/api/portal/sync"
