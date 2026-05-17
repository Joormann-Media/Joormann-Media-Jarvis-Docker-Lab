#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "lab_config.json"
INTENTS_PATH = BASE_DIR / "config" / "intent_suggestions.json"
RUNTIME_DIR = BASE_DIR / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")
app = Flask(__name__)
DEFAULT_LAB_PORT = "5103"


def _load_lab_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "lab_name": os.getenv("LAB_NAME", "Joormann-Media-Jarvis-Docker-Lab"),
        "portal_url": os.getenv("PORTAL_URL", "").strip(),
        "machine_id": os.getenv("PORTAL_MACHINE_ID", "").strip(),
        "node_slug": "jarvis-docker-lab",
        "client_id": "",
        "api_key": "",
        "docker_timeout": int(os.getenv("DOCKER_TIMEOUT", "20")),
        "updated_at": 0,
    }
    try:
        if CONFIG_PATH.exists():
            file_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(file_cfg, dict):
                defaults.update(file_cfg)
    except Exception:
        pass
    return defaults


def _save_lab_config(updates: dict[str, Any]) -> None:
    cfg = _load_lab_config()
    cfg.update(updates)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_machine_id(cfg: dict[str, Any]) -> str:
    env = str(os.getenv("PORTAL_MACHINE_ID", "")).strip()
    if env:
        return env
    raw_cfg = str(cfg.get("machine_id") or "").strip()
    if raw_cfg:
        return raw_cfg
    candidates = [
        os.getenv("DEVICE_PORTAL_DEVICE_JSON", "").strip(),
        str(Path.home() / "projects" / "Joormann-Media-Deviceportal" / "var" / "data" / "device.json"),
        "/opt/joormann-media-deviceportal/var/data/device.json",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                value = str(data.get("machine_id") or "").strip()
                if value:
                    return value
        except Exception:
            continue
    return f"docker-lab-{socket.gethostname().split('.', 1)[0]}"


def _resolve_portal_url(cfg: dict[str, Any]) -> str:
    env = str(os.getenv("PORTAL_URL", "")).strip()
    if env:
        return env
    raw_cfg = str(cfg.get("portal_url") or "").strip()
    if raw_cfg:
        return raw_cfg
    candidates = [
        os.getenv("DEVICE_PORTAL_CONFIG_JSON", "").strip(),
        str(Path.home() / "projects" / "Joormann-Media-Deviceportal" / "var" / "data" / "config.json"),
        "/opt/joormann-media-deviceportal/var/data/config.json",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                for key in ("admin_base_url", "portal_url", "base_url"):
                    value = str(data.get(key) or "").strip()
                    if value:
                        return value
        except Exception:
            continue
    return ""


def _run_cmd(args: list[str], timeout: int | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout or 20, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def _docker_ok() -> tuple[bool, str]:
    code, out, err = _run_cmd(["docker", "info", "--format", "{{json .ServerVersion}}"])
    if code == 0 and out:
        return True, out.replace('"', '')
    return False, err or "Docker daemon nicht erreichbar"


def _docker_daemon_config() -> dict[str, Any]:
    daemon_path = Path("/etc/docker/daemon.json")
    if not daemon_path.exists():
        return {"exists": False, "path": str(daemon_path), "config": {}}
    try:
        data = json.loads(daemon_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"exists": True, "path": str(daemon_path), "config": {}, "parse_error": str(exc)}
    return {"exists": True, "path": str(daemon_path), "config": data}


def _docker_system_df() -> dict[str, Any]:
    code, out, err = _run_cmd(["docker", "system", "df", "--format", "json"])
    if code != 0:
        return {"ok": False, "error": err}
    lines = [x for x in out.splitlines() if x.strip()]
    parsed: list[dict[str, Any]] = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except Exception:
            continue
    return {"ok": True, "rows": parsed}


def _docker_containers(all_containers: bool = True) -> list[dict[str, Any]]:
    fmt = "{{json .}}"
    cmd = ["docker", "ps", "--format", fmt]
    if all_containers:
        cmd.insert(2, "-a")
    code, out, _ = _run_cmd(cmd)
    if code != 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _docker_container_stats() -> dict[str, dict[str, Any]]:
    code, out, _ = _run_cmd(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=30)
    if code != 0:
        return {}
    stats: dict[str, dict[str, Any]] = {}
    for line in out.splitlines():
        try:
            item = json.loads(line)
            key = str(item.get("ID") or "").strip()
            if key:
                stats[key] = item
        except Exception:
            continue
    return stats


def _docker_inspect(container_id: str) -> dict[str, Any]:
    code, out, err = _run_cmd(["docker", "inspect", container_id], timeout=30)
    if code != 0:
        return {"ok": False, "error": err}
    try:
        data = json.loads(out)
        if not isinstance(data, list) or not data:
            return {"ok": False, "error": "inspect_leer"}
        obj = data[0]
        return {
            "ok": True,
            "id": obj.get("Id"),
            "name": str(obj.get("Name") or "").lstrip("/"),
            "state": obj.get("State") or {},
            "mounts": obj.get("Mounts") or [],
            "host_config": obj.get("HostConfig") or {},
            "network_settings": obj.get("NetworkSettings") or {},
            "config": obj.get("Config") or {},
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _docker_action(action: str, container_id: str) -> tuple[dict[str, Any], int]:
    if action not in {"start", "stop", "restart"}:
        return {"ok": False, "error": "action_invalid"}, 400
    code, _, err = _run_cmd(["docker", action, container_id], timeout=40)
    if code != 0:
        return {"ok": False, "error": err}, 502
    return {"ok": True, "action": action, "container": container_id}, 200


def _docker_prune(include_volumes: bool) -> tuple[dict[str, Any], int]:
    cmd = ["docker", "system", "prune", "-f"]
    if include_volumes:
        cmd.append("--volumes")
    code, out, err = _run_cmd(cmd, timeout=180)
    if code != 0:
        return {"ok": False, "error": err}, 502
    return {"ok": True, "output": out}, 200


def _local_peer_modules() -> list[dict[str, Any]]:
    mapping = {
        "docker-lab": "Docker-Lab",
        "search-lab": "Search-Lab",
        "smarthome": "Smarthome-Lab",
        "ocr-lab": "OCR-Lab",
        "llm-lab": "LLM-Lab",
    }
    def label(name: str) -> str:
        low = name.lower()
        for key, value in mapping.items():
            if key in low:
                return value
        return name or "Module"

    current_port = int(os.getenv("FLASK_PORT", DEFAULT_LAB_PORT))
    seen: set[int] = set()
    peers: list[dict[str, Any]] = []
    path = Path(os.getenv("DEVICE_PORTAL_CONFIG_JSON") or str(Path.home() / "projects" / "Joormann-Media-Deviceportal" / "var" / "data" / "config.json"))
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data.get("autodiscover_services") if isinstance(data, dict) else []
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        port_i = int(row.get("port"))
                    except Exception:
                        continue
                    if port_i <= 0 or port_i in seen:
                        continue
                    seen.add(port_i)
                    service_name = str(row.get("service_name") or row.get("name") or "Module")
                    peers.append({"name": label(service_name), "serviceName": service_name, "port": port_i, "source": "deviceportal-autodiscover"})
    except Exception:
        pass
    if current_port not in seen:
        peers.append({"name": "Docker-Lab", "serviceName": "joormann-media-jarvis-docker-lab.service", "port": current_port, "source": "self"})
    peers.sort(key=lambda x: int(x.get("port") or 0))
    return peers


def _portal_status_payload() -> dict[str, Any]:
    cfg = _load_lab_config()
    machine_id = _resolve_machine_id(cfg)
    portal_url = _resolve_portal_url(cfg)
    node_slug = str(cfg.get("node_slug") or "jarvis-docker-lab")
    client_id = str(cfg.get("client_id") or "").strip()
    registered = bool(portal_url and client_id)
    return {"ok": True, "registered": registered, "nodeName": f"Docker-Lab ({socket.gethostname()})", "nodeSlug": node_slug, "machineId": machine_id, "portalUrl": portal_url or None, "clientId": client_id or None}


def _mcp_actions() -> list[dict[str, Any]]:
    return [
        {"id": "docker_status", "tool_name": "docker_status", "display_name": "Docker Status", "enabled": True, "candidate": False, "phase": "readonly", "permission_key": "mcp.docker.status", "category": "docker.status", "risk_level": "safe", "description": "Prüft Docker-Daemon und Basisstatus.", "schema": {"type": "object", "properties": {}, "required": []}},
        {"id": "docker_list_containers", "tool_name": "docker_list_containers", "display_name": "Container Liste", "enabled": True, "candidate": False, "phase": "readonly", "permission_key": "mcp.docker.containers.list", "category": "docker.containers", "risk_level": "safe", "description": "Listet Container inkl. Status/Ressourcen.", "schema": {"type": "object", "properties": {"all": {"type": "boolean", "default": True}}, "required": []}},
        {"id": "docker_inspect_container", "tool_name": "docker_inspect_container", "display_name": "Container Inspect", "enabled": True, "candidate": False, "phase": "readonly", "permission_key": "mcp.docker.containers.inspect", "category": "docker.containers", "risk_level": "safe", "description": "Zeigt Mounts/Netzwerk/Config eines Containers.", "schema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
        {"id": "docker_start_container", "tool_name": "docker_start_container", "display_name": "Container Start", "enabled": True, "candidate": True, "phase": "candidate", "permission_key": "mcp.docker.containers.start", "category": "docker.containers", "risk_level": "medium", "description": "Startet einen Container.", "schema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
        {"id": "docker_stop_container", "tool_name": "docker_stop_container", "display_name": "Container Stop", "enabled": True, "candidate": True, "phase": "candidate", "permission_key": "mcp.docker.containers.stop", "category": "docker.containers", "risk_level": "medium", "description": "Stoppt einen Container.", "schema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
        {"id": "docker_restart_container", "tool_name": "docker_restart_container", "display_name": "Container Restart", "enabled": True, "candidate": True, "phase": "candidate", "permission_key": "mcp.docker.containers.restart", "category": "docker.containers", "risk_level": "medium", "description": "Restart eines Containers.", "schema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]}},
        {"id": "docker_prune_system", "tool_name": "docker_prune_system", "display_name": "Docker Cleanup", "enabled": True, "candidate": True, "phase": "candidate", "permission_key": "mcp.docker.system.prune", "category": "docker.cleanup", "risk_level": "high", "description": "Bereinigt ungenutzte Docker-Ressourcen.", "schema": {"type": "object", "properties": {"volumes": {"type": "boolean", "default": False}}, "required": []}},
        {"id": "docker_daemon_config_get", "tool_name": "docker_daemon_config_get", "display_name": "Daemon Config", "enabled": True, "candidate": False, "phase": "readonly", "permission_key": "mcp.docker.config.get", "category": "docker.config", "risk_level": "safe", "description": "Liest /etc/docker/daemon.json.", "schema": {"type": "object", "properties": {}, "required": []}},
    ]


def _do_portal_sync() -> tuple[int, dict[str, Any]]:
    cfg = _load_lab_config()
    portal_url = _resolve_portal_url(cfg)
    client_id = str(cfg.get("client_id") or "").strip()
    api_key = str(cfg.get("api_key") or "").strip()
    node_slug = str(cfg.get("node_slug") or "jarvis-docker-lab").strip()
    if not portal_url or not client_id:
        return 502, {"ok": False, "node_ok": False, "node_sync_ok": False, "mcp_ok": False, "status": "not_linked", "message": "Node noch nicht verknüpft."}

    port = int(os.getenv("FLASK_PORT", DEFAULT_LAB_PORT))
    payload = {
        "service": "docker-lab",
        "serviceSlug": node_slug,
        "machineId": _resolve_machine_id(cfg),
        "host": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "port": port,
        "baseUrl": f"http://{socket.gethostbyname(socket.gethostname())}:{port}",
        "capabilities": ["docker.status", "docker.containers", "docker.system", "docker.cleanup", "docker.config", "mcp"],
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json", "X-Client-Id": client_id, "X-Jarvis-Api-Key": api_key, "X-API-Key": api_key}
    node_sync_ok = False
    mcp_ok = False
    try:
        r1 = requests.post(f"{portal_url.rstrip('/')}/api/jarvis/node/sync", json=payload, headers=headers, timeout=20)
        node_sync_ok = 200 <= r1.status_code < 300
    except Exception:
        node_sync_ok = False
    try:
        intents = []
        for action in _mcp_actions():
            intents.append({
                "intentKey": action["tool_name"],
                "name": action["display_name"],
                "actionKey": action["tool_name"],
                "permissionKey": action["permission_key"],
                "category": action["category"],
                "description": action["description"],
                "requiredParams": list((action.get("schema") or {}).get("required") or []),
                "optionalParams": [k for k in ((action.get("schema") or {}).get("properties") or {}) if k not in ((action.get("schema") or {}).get("required") or [])],
                "operation": "read" if action.get("risk_level") == "safe" else "write",
                "endpointTemplate": "/api/mcp/actions/execute",
                "phase": action.get("phase"),
                "riskLevel": action.get("risk_level"),
                "source": "mcp",
                "isActive": bool(action.get("enabled", True)),
            })
        r2 = requests.post(f"{portal_url.rstrip('/')}/api/jarvis/node/intents/sync", json={"intents": intents}, headers=headers, timeout=20)
        mcp_ok = 200 <= r2.status_code < 300
    except Exception:
        mcp_ok = False

    ok = node_sync_ok and mcp_ok
    return (200 if ok else 502), {"ok": ok, "node_ok": True, "node_sync_ok": node_sync_ok, "mcp_ok": mcp_ok}


@app.get("/")
def index():
    cfg = _load_lab_config()
    ok, version = _docker_ok()
    return render_template("index.html", active_page="dashboard", lab_name=cfg.get("lab_name"), docker_ok=ok, docker_version=version)


@app.get("/containers")
def containers_page():
    return render_template("containers.html", active_page="containers")


@app.get("/status")
def status_page():
    return render_template("status.html", active_page="status")


@app.get("/mcp-actions")
def mcp_actions_page():
    return render_template("mcp_actions.html", active_page="mcp")


@app.get("/link")
def link_page():
    return render_template("link.html", active_page="link", portal=_portal_status_payload())


@app.get("/info")
def info_page():
    return render_template("info.html", active_page="info", daemon=_docker_daemon_config())


@app.get("/health")
def health():
    ok, version = _docker_ok()
    return jsonify(ok=True, service="docker-lab", docker_ok=ok, docker_version=version, ts=int(time.time()))


@app.get("/api/health")
def api_health():
    return health()


@app.get("/api/status")
def api_status():
    cfg = _load_lab_config()
    ok, version = _docker_ok()
    return jsonify(ok=True, service="docker-lab", version="1.0.0", docker_ok=ok, docker_version=version, machine_id=_resolve_machine_id(cfg), portal_url=_resolve_portal_url(cfg) or None)


@app.get("/api/docker/status")
def api_docker_status():
    ok, version = _docker_ok()
    info = {}
    if ok:
        code, out, _ = _run_cmd(["docker", "info", "--format", "{{json .}}"], timeout=30)
        if code == 0 and out:
            try:
                info = json.loads(out)
            except Exception:
                info = {}
    return jsonify(ok=ok, version=version if ok else None, info=info)


@app.get("/api/docker/containers")
def api_docker_containers():
    all_flag = str(request.args.get("all", "1")).strip().lower() not in {"0", "false", "no"}
    rows = _docker_containers(all_containers=all_flag)
    stats = _docker_container_stats()
    out: list[dict[str, Any]] = []
    for row in rows:
        cid = str(row.get("ID") or "")
        st = stats.get(cid, {})
        out.append({
            "id": cid,
            "name": row.get("Names"),
            "image": row.get("Image"),
            "status": row.get("Status"),
            "state": row.get("State"),
            "ports": row.get("Ports"),
            "running_for": row.get("RunningFor"),
            "cpu": st.get("CPUPerc"),
            "mem": st.get("MemUsage"),
            "mem_perc": st.get("MemPerc"),
            "net_io": st.get("NetIO"),
            "block_io": st.get("BlockIO"),
            "pids": st.get("PIDs"),
        })
    return jsonify(ok=True, count=len(out), containers=out)


@app.get("/api/docker/container/<container_id>/inspect")
def api_docker_inspect(container_id: str):
    payload = _docker_inspect(container_id)
    return jsonify(payload), (200 if payload.get("ok") else 404)


@app.post("/api/docker/container/<container_id>/start")
def api_docker_start(container_id: str):
    payload, code = _docker_action("start", container_id)
    return jsonify(payload), code


@app.post("/api/docker/container/<container_id>/stop")
def api_docker_stop(container_id: str):
    payload, code = _docker_action("stop", container_id)
    return jsonify(payload), code


@app.post("/api/docker/container/<container_id>/restart")
def api_docker_restart(container_id: str):
    payload, code = _docker_action("restart", container_id)
    return jsonify(payload), code


@app.post("/api/docker/prune")
def api_docker_prune():
    body = request.get_json(silent=True) or {}
    include_volumes = bool(body.get("volumes", False))
    payload, code = _docker_prune(include_volumes)
    return jsonify(payload), code


@app.get("/api/docker/system/df")
def api_docker_system_df():
    return jsonify(_docker_system_df())


@app.get("/api/docker/config")
def api_docker_config():
    return jsonify(ok=True, daemon=_docker_daemon_config())


@app.post("/api/docker/config/update")
def api_docker_config_update():
    body = request.get_json(silent=True) or {}
    config = body.get("config")
    if not isinstance(config, dict):
        return jsonify(ok=False, error="config_invalid"), 400
    payload = {
        "ok": False,
        "message": "Direktes Schreiben nach /etc/docker/daemon.json aus dem Lab ist absichtlich blockiert.",
        "next_steps": [
            "Nutze sudo auf Shell für /etc/docker/daemon.json",
            "sudo systemctl daemon-reload",
            "sudo systemctl restart docker"
        ],
        "proposed": config,
    }
    return jsonify(payload), 403


@app.get("/api/capabilities")
def api_capabilities():
    return jsonify(ok=True, capabilities=["docker.status", "docker.containers", "docker.system", "docker.cleanup", "docker.config"], mcp_actions=[x["tool_name"] for x in _mcp_actions()])


@app.get("/api/mcp/actions")
def api_mcp_actions():
    return jsonify(ok=True, count=len(_mcp_actions()), actions=_mcp_actions())


@app.get("/api/mcp/status")
def api_mcp_status():
    return jsonify(ok=True, service="docker-lab", action_count=len(_mcp_actions()))


@app.post("/api/mcp/actions/execute")
def api_mcp_execute():
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or body.get("tool_name") or "").strip()
    params = body.get("params") if isinstance(body.get("params"), dict) else body

    if action == "docker_status":
        return api_docker_status()
    if action == "docker_list_containers":
        all_flag = bool(params.get("all", True))
        with app.test_request_context(f"/api/docker/containers?all={'1' if all_flag else '0'}", method="GET"):
            return api_docker_containers()
    if action == "docker_inspect_container":
        c = str(params.get("container") or "").strip()
        if not c:
            return jsonify(ok=False, error="container_missing"), 400
        return api_docker_inspect(c)
    if action == "docker_start_container":
        c = str(params.get("container") or "").strip()
        if not c:
            return jsonify(ok=False, error="container_missing"), 400
        return api_docker_start(c)
    if action == "docker_stop_container":
        c = str(params.get("container") or "").strip()
        if not c:
            return jsonify(ok=False, error="container_missing"), 400
        return api_docker_stop(c)
    if action == "docker_restart_container":
        c = str(params.get("container") or "").strip()
        if not c:
            return jsonify(ok=False, error="container_missing"), 400
        return api_docker_restart(c)
    if action == "docker_prune_system":
        with app.test_request_context("/api/docker/prune", method="POST", json={"volumes": bool(params.get("volumes", False))}):
            return api_docker_prune()
    if action == "docker_daemon_config_get":
        return api_docker_config()
    return jsonify(ok=False, error="action_not_supported", action=action), 400


@app.get("/api/portal/status")
def api_portal_status():
    return jsonify(_portal_status_payload())


@app.get("/api/portal/peers")
def api_portal_peers():
    return jsonify(ok=True, data={"peers": _local_peer_modules()})


@app.post("/api/portal/register")
def api_portal_register():
    body = request.get_json(silent=True) or {}
    updates = {
        "portal_url": str(body.get("portal_url") or "").strip().rstrip("/"),
        "node_slug": str(body.get("node_slug") or "jarvis-docker-lab").strip(),
        "client_id": str(body.get("client_id") or "").strip(),
        "api_key": str(body.get("api_key") or "").strip(),
        "updated_at": int(time.time()),
    }
    _save_lab_config(updates)
    return jsonify(_portal_status_payload())


@app.post("/api/portal/sync")
def api_portal_sync():
    code, payload = _do_portal_sync()
    return jsonify(payload), code


@app.get("/api/update/status")
def api_update_status():
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=BASE_DIR, check=True, capture_output=True)
        subprocess.run(["git", "fetch", "--quiet"], cwd=BASE_DIR, check=True)
        behind = subprocess.run(["bash", "-lc", "git rev-list --count HEAD..@{u}"], cwd=BASE_DIR, check=True, capture_output=True, text=True)
        behind_count = int((behind.stdout or "0").strip() or "0")
        return jsonify(ok=True, update_available=behind_count > 0, behind=behind_count)
    except Exception as exc:
        return jsonify(ok=False, update_available=False, message=str(exc)), 500


@app.post("/api/update/apply")
def api_update_apply():
    try:
        subprocess.run(["git", "pull", "--ff-only"], cwd=BASE_DIR, check=True, capture_output=True)
        return jsonify(ok=True, applied=True)
    except Exception as exc:
        return jsonify(ok=False, applied=False, message=str(exc)), 500


@app.get("/api/intents")
def api_intents():
    try:
        data = json.loads(INTENTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"ok": False, "intents": []}
    if isinstance(data, dict):
        data.setdefault("ok", True)
    return jsonify(data)


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", DEFAULT_LAB_PORT))
    debug = str(os.getenv("FLASK_DEBUG", "0")).lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug)
