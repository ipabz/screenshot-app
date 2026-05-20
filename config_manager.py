from __future__ import annotations

import json
import socket
from copy import deepcopy
from pathlib import Path
from typing import Any


CONFIG_PATH = Path("config.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "hotkey": "ctrl+shift+s",
    "port": 8892,
    "save_directory": "screenshots",
    "database_path": "screenshots/gallery.sqlite3",
    "sharing": {
        "lan_enabled": False,
        "copy_after_capture": "local",
    },
}


def _merge_config(defaults: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)

    with config_path.open("r", encoding="utf-8") as config_file:
        raw_config = json.load(config_file)

    if not isinstance(raw_config, dict):
        raise ValueError("config.json must contain a JSON object")

    config = _merge_config(DEFAULT_CONFIG, raw_config)
    config["port"] = int(config["port"])
    config["save_directory"] = str(config["save_directory"])
    config["database_path"] = str(config["database_path"])

    sharing = config["sharing"]
    sharing["lan_enabled"] = bool(sharing.get("lan_enabled", False))
    copy_after_capture = sharing.get("copy_after_capture", "local")
    if copy_after_capture not in {"local", "lan", "none"}:
        copy_after_capture = "local"
    sharing["copy_after_capture"] = copy_after_capture

    return config


def save_config(config: dict[str, Any], path: str | Path = CONFIG_PATH) -> None:
    config_path = Path(path)
    with config_path.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)
        config_file.write("\n")


def get_save_dir(config: dict[str, Any]) -> Path:
    return Path(config["save_directory"]).resolve()


def get_database_path(config: dict[str, Any]) -> Path:
    return Path(config["database_path"]).resolve()


def get_server_host(config: dict[str, Any]) -> str:
    return "0.0.0.0" if config["sharing"]["lan_enabled"] else "127.0.0.1"


def get_local_base_url(config: dict[str, Any]) -> str:
    return f"http://127.0.0.1:{config['port']}"


def get_lan_ip() -> str:
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        if ip_address and not ip_address.startswith("127."):
            return ip_address
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def get_lan_base_url(config: dict[str, Any]) -> str:
    return f"http://{get_lan_ip()}:{config['port']}"
