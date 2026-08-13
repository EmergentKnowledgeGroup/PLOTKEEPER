from __future__ import annotations

import json
import os
import socket
from pathlib import Path

LOOPBACK_HOST = "127.0.0.1"
DYNAMIC_PORT_MIN = 49152
DYNAMIC_PORT_MAX = 65535
CONNECTOR_NAME = "plotkeeper-connector.json"


def connector_path(repo_root: str | os.PathLike[str]) -> Path:
    return Path(repo_root).resolve() / "runtime" / CONNECTOR_NAME


def read_connector(path: str | os.PathLike[str]) -> dict[str, object]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        host, port = str(payload["host"]), int(payload["port"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Plotkeeper connector: {target}") from exc
    if host != LOOPBACK_HOST or not 1 <= port <= 65535:
        raise ValueError(f"invalid Plotkeeper connector: {target}")
    return {"host": host, "port": port, "url": f"http://{host}:{port}", "path": str(target.resolve())}


def choose_private_port(host: str = LOOPBACK_HOST) -> int:
    if host != LOOPBACK_HOST:
        raise ValueError("automatic connectors are loopback-only")
    for _ in range(32):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
            port = int(probe.getsockname()[1])
        if DYNAMIC_PORT_MIN <= port <= DYNAMIC_PORT_MAX:
            return port
    raise RuntimeError("Windows did not provide a dynamic/private loopback port")


def write_connector(path: str | os.PathLike[str], port: int, host: str = LOOPBACK_HOST) -> dict[str, object]:
    port = int(port)
    if host != LOOPBACK_HOST or not 1 <= port <= 65535:
        raise ValueError("Plotkeeper connectors must use a valid 127.0.0.1 port")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps({"host": host, "port": port, "url": f"http://{host}:{port}"}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return read_connector(target)


def ensure_connector(path: str | os.PathLike[str], explicit_port: int | None = None) -> dict[str, object]:
    target = Path(path)
    if explicit_port is not None:
        return write_connector(target, explicit_port)
    if target.is_file():
        return read_connector(target)
    return write_connector(target, choose_private_port())
