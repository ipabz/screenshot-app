from __future__ import annotations

import threading
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.serving import make_server

from config_manager import (
    CONFIG_PATH,
    get_database_path,
    get_lan_base_url,
    get_local_base_url,
    get_save_dir,
    get_server_host,
    load_config,
    save_config,
)
from gallery_store import GalleryStore


LOCAL_REMOTE_ADDRS = {"127.0.0.1", "::1"}


def is_local_request() -> bool:
    remote_addr = request.remote_addr or ""
    return remote_addr in LOCAL_REMOTE_ADDRS or remote_addr.startswith("::ffff:127.")


def local_only(route):
    @wraps(route)
    def wrapped(*args, **kwargs):
        if not is_local_request():
            abort(403)
        return route(*args, **kwargs)

    return wrapped


def create_app(config_path: str | Path = CONFIG_PATH) -> Flask:
    app = Flask(__name__)

    def current_config() -> dict[str, Any]:
        return load_config(config_path)

    def current_store() -> GalleryStore:
        config = current_config()
        return GalleryStore(get_database_path(config))

    @app.route("/")
    @local_only
    def gallery():
        return render_template("gallery.html")

    @app.route("/api/settings", methods=["GET"])
    @local_only
    def get_settings():
        config = current_config()
        return jsonify(_settings_payload(config, app.config.get("BOUND_HOST")))

    @app.route("/api/settings", methods=["PATCH"])
    @local_only
    def update_settings():
        config = current_config()
        data = request.get_json(silent=True) or {}

        if "lan_enabled" in data:
            config["sharing"]["lan_enabled"] = bool(data["lan_enabled"])

        if "copy_after_capture" in data:
            copy_after_capture = data["copy_after_capture"]
            if copy_after_capture not in {"local", "lan", "none"}:
                return jsonify({"error": "copy_after_capture must be local, lan, or none"}), 400
            config["sharing"]["copy_after_capture"] = copy_after_capture

        save_config(config, config_path)
        return jsonify(_settings_payload(config, app.config.get("BOUND_HOST")))

    @app.route("/api/captures", methods=["GET"])
    @local_only
    def list_captures():
        config = current_config()
        store = current_store()
        store.sync_existing_files(get_save_dir(config))
        captures = [_capture_payload(config, capture) for capture in store.list_captures()]
        return jsonify({"captures": captures})

    @app.route("/api/capture", methods=["POST"])
    @local_only
    def start_capture():
        from capture import start_capture_ui

        threading.Thread(target=start_capture_ui, daemon=True).start()
        return jsonify({"started": True}), 202

    @app.route("/api/captures/<int:capture_id>/share", methods=["POST"])
    @local_only
    def set_capture_share(capture_id: int):
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        config = current_config()
        capture = current_store().set_share_enabled(capture_id, enabled)
        if capture is None:
            abort(404)
        return jsonify({"capture": _capture_payload(config, capture)})

    @app.route("/api/captures/<int:capture_id>", methods=["DELETE"])
    @local_only
    def delete_capture(capture_id: int):
        config = current_config()
        store = current_store()
        capture = store.get_capture(capture_id)
        if capture is None:
            abort(404)

        try:
            file_path = _capture_path(config, capture, require_exists=False)
            if file_path.exists():
                file_path.unlink()
        except ValueError:
            pass

        store.delete_capture(capture_id)
        return "", 204

    @app.route("/captures/<int:capture_id>/file")
    @local_only
    def serve_local_capture(capture_id: int):
        config = current_config()
        capture = current_store().get_capture(capture_id)
        if capture is None:
            abort(404)
        return _serve_capture_file(config, capture)

    @app.route("/s/<token>")
    def serve_shared_capture(token: str):
        config = current_config()
        if not config["sharing"]["lan_enabled"]:
            abort(404)

        capture = current_store().get_by_token(token)
        if capture is None:
            abort(404)
        return _serve_capture_file(config, capture)

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    return app


class ServerRunner:
    def __init__(self, config_path: str | Path = CONFIG_PATH):
        self.config_path = Path(config_path)
        self._server = None
        self._thread = None
        self.host = None
        self.port = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._server is not None:
                return

            config = load_config(self.config_path)
            get_save_dir(config).mkdir(parents=True, exist_ok=True)
            GalleryStore(get_database_path(config)).sync_existing_files(get_save_dir(config))

            self.host = get_server_host(config)
            self.port = config["port"]
            app = create_app(self.config_path)
            app.config["BOUND_HOST"] = self.host
            app.config["BOUND_PORT"] = self.port

            self._server = make_server(self.host, self.port, app, threaded=True)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None

        if server is not None:
            server.shutdown()
            server.server_close()

        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    def restart(self) -> None:
        self.stop()
        self.start()


def run_server(port: int | None = None) -> None:
    config = load_config()
    if port is not None:
        config["port"] = int(port)

    get_save_dir(config).mkdir(parents=True, exist_ok=True)
    GalleryStore(get_database_path(config)).sync_existing_files(get_save_dir(config))

    app = create_app()
    host = get_server_host(config)
    app.config["BOUND_HOST"] = host
    app.config["BOUND_PORT"] = config["port"]
    app.run(host=host, port=config["port"], threaded=True)


def _settings_payload(config: dict[str, Any], bound_host: str | None) -> dict[str, Any]:
    desired_host = get_server_host(config)
    return {
        "hotkey": config["hotkey"],
        "port": config["port"],
        "save_directory": config["save_directory"],
        "sharing": config["sharing"],
        "local_base_url": get_local_base_url(config),
        "lan_base_url": get_lan_base_url(config),
        "server_host": bound_host or desired_host,
        "desired_host": desired_host,
        "restart_required": bound_host is not None and bound_host != desired_host,
    }


def _capture_payload(config: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    local_url = f"{get_local_base_url(config)}/captures/{capture['id']}/file"
    lan_url = None
    if config["sharing"]["lan_enabled"] and capture.get("share_token"):
        lan_url = f"{get_lan_base_url(config)}/s/{capture['share_token']}"

    return {
        "id": capture["id"],
        "filename": capture["filename"],
        "created_at": capture["created_at"],
        "width": capture["width"],
        "height": capture["height"],
        "file_size": capture["file_size"],
        "share_enabled": capture["share_enabled"],
        "shared_at": capture["shared_at"],
        "local_url": local_url,
        "lan_url": lan_url,
    }


def _capture_path(
    config: dict[str, Any], capture: dict[str, Any], require_exists: bool = True
) -> Path:
    save_dir = get_save_dir(config)
    file_path = Path(capture["path"]).resolve()
    try:
        file_path.relative_to(save_dir)
    except ValueError as exc:
        raise ValueError("Capture path is outside the screenshots directory") from exc

    if require_exists and not file_path.exists():
        raise FileNotFoundError(file_path)
    return file_path


def _serve_capture_file(config: dict[str, Any], capture: dict[str, Any]):
    try:
        file_path = _capture_path(config, capture)
    except (FileNotFoundError, ValueError):
        abort(404)

    response = send_file(file_path)
    response.headers["Cache-Control"] = "private, max-age=60"
    return response


if __name__ == "__main__":
    run_server()
