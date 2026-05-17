# Joormann-Media-Jarvis-Docker-Lab

Flask-basiertes Jarvis-Lab zur Docker-Verwaltung: Status, Container-Management, Resource-Ansicht, Mounts/Inspect, Cleanup, Daemon-Konfig-Ansicht und MCP/Panel-Integration.

## Start

```bash
cp .env.example .env
./scripts/start-dev.sh
```

## Wichtige ENV Variablen

- `FLASK_PORT` (Standard: `5103`)
- `PORTAL_URL`
- `PORTAL_MACHINE_ID`
- `DOCKER_TIMEOUT`

## Seiten

- `/` Dashboard
- `/containers` Container-Liste + Start/Stop/Restart + Inspect
- `/status` Service-Status
- `/mcp-actions` MCP-Actionliste
- `/link` Panel-Linkstatus
- `/info` Docker-Daemon-Konfiguration

## API Endpunkte

- `GET /health`
- `GET /api/status`
- `GET /api/docker/status`
- `GET /api/docker/containers?all=1`
- `GET /api/docker/container/<id>/inspect`
- `POST /api/docker/container/<id>/start`
- `POST /api/docker/container/<id>/stop`
- `POST /api/docker/container/<id>/restart`
- `POST /api/docker/prune`
- `GET /api/docker/system/df`
- `GET /api/docker/config`
- `POST /api/docker/config/update` (sicherheitsbedingt bewusst blockiert)
- `GET /api/capabilities`
- `GET /api/mcp/actions`
- `GET /api/mcp/status`
- `POST /api/mcp/actions/execute`
- `GET /api/portal/status`
- `GET /api/portal/peers`
- `POST /api/portal/register`
- `POST /api/portal/sync`
- `GET /api/intents`

## MCP Actions

- `docker_status` (safe)
- `docker_list_containers` (safe)
- `docker_inspect_container` (safe)
- `docker_start_container` (medium/candidate)
- `docker_stop_container` (medium/candidate)
- `docker_restart_container` (medium/candidate)
- `docker_prune_system` (high/candidate)
- `docker_daemon_config_get` (safe)

## Beispiel-cURL

```bash
curl -s http://127.0.0.1:5103/health
curl -s http://127.0.0.1:5103/api/docker/containers?all=1
curl -s http://127.0.0.1:5103/api/docker/system/df
curl -s -X POST http://127.0.0.1:5103/api/docker/prune -H 'Content-Type: application/json' -d '{"volumes":false}'
```
