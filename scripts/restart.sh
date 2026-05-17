#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf "[restart] Stoppe Modul ...\n"
"$SCRIPT_DIR/stop-dev.sh" || true
sleep 1
printf "[restart] Starte Modul ...\n"
exec "$SCRIPT_DIR/start-dev.sh"
