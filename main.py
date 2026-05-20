import os
import sys
import threading
import webbrowser

import keyboard
import pystray
from PIL import Image, ImageDraw

from capture import start_capture_ui
from config_manager import get_lan_base_url, get_local_base_url, get_save_dir, load_config, save_config
from server import ServerRunner


APP_NAME = "Screenshot App"


def log(message):
    if sys.stdout:
        print(message)


def create_tray_image():
    scale = 4
    size = 64
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(x1, y1, x2, y2):
        return tuple(v * scale for v in (x1, y1, x2, y2))

    def width(value):
        return value * scale

    # Keep the mark large and simple so it remains legible in the Windows tray.
    draw.rounded_rectangle(
        box(2, 7, 62, 57),
        radius=12 * scale,
        fill="#0f172a",
    )
    draw.rounded_rectangle(
        box(19, 2, 45, 15),
        radius=5 * scale,
        fill="#0f172a",
    )
    draw.rectangle(box(23, 11, 41, 19), fill="#0f172a")

    accent = "#22d3ee"
    draw.ellipse(
        box(17, 17, 47, 47),
        fill="#e0f2fe",
        outline=accent,
        width=width(6),
    )
    draw.ellipse(box(26, 26, 38, 38), fill="#0f172a")

    draw.rounded_rectangle(box(45, 16, 55, 24), radius=3 * scale, fill="#facc15")

    resample_filter = getattr(Image, "Resampling", Image).LANCZOS
    return image.resize((size, size), resample_filter)


def notify(icon, message, title=APP_NAME):
    log(message)
    try:
        icon.notify(message, title)
    except Exception:
        pass


def capture_from_tray(icon):
    def on_complete(result):
        if result.get("clipboard_copied"):
            notify(icon, f"Captured {result['filename']} and copied the link.")
        else:
            notify(icon, f"Captured {result['filename']}.")

    def on_error(exc):
        notify(icon, f"Capture failed: {exc}")

    threading.Thread(
        target=lambda: start_capture_ui(on_complete=on_complete, on_error=on_error),
        daemon=True,
    ).start()


def open_gallery():
    config = load_config()
    webbrowser.open(f"{get_local_base_url(config)}/")


def open_screenshots_folder():
    save_dir = get_save_dir(load_config())
    save_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(save_dir)
    else:
        webbrowser.open(save_dir.as_uri())


def toggle_lan_sharing(icon, server_runner):
    config = load_config()
    config["sharing"]["lan_enabled"] = not config["sharing"]["lan_enabled"]
    save_config(config)

    try:
        server_runner.restart()
    except OSError as exc:
        notify(icon, f"Could not restart server: {exc}")
        return

    mode = "enabled" if config["sharing"]["lan_enabled"] else "disabled"
    url = get_lan_base_url(config) if config["sharing"]["lan_enabled"] else get_local_base_url(config)
    notify(icon, f"LAN sharing {mode}. Server: {url}")
    try:
        icon.update_menu()
    except Exception:
        pass


def quit_app(icon, server_runner):
    keyboard.unhook_all()
    server_runner.stop()
    icon.stop()


def lan_enabled_label(_item):
    return "Disable LAN sharing" if load_config()["sharing"]["lan_enabled"] else "Enable LAN sharing"


def lan_checked(_item):
    return load_config()["sharing"]["lan_enabled"]


def build_tray_icon(hotkey, server_runner):
    config = load_config()
    menu = pystray.Menu(
        pystray.MenuItem("Capture now", lambda icon, item: capture_from_tray(icon)),
        pystray.MenuItem("Open gallery", lambda icon, item: open_gallery()),
        pystray.MenuItem("Open screenshots folder", lambda icon, item: open_screenshots_folder()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lan_enabled_label,
            lambda icon, item: toggle_lan_sharing(icon, server_runner),
            checked=lan_checked,
        ),
        pystray.MenuItem(f"Hotkey: {hotkey}", None, enabled=False),
        pystray.MenuItem(f"Local: {get_local_base_url(config)}", None, enabled=False),
        pystray.MenuItem("Quit", lambda icon, item: quit_app(icon, server_runner)),
    )

    return pystray.Icon(APP_NAME, create_tray_image(), APP_NAME, menu)


def main():
    try:
        config = load_config()
    except Exception as exc:
        log(f"Could not load config: {exc}")
        return

    save_dir = get_save_dir(config)
    save_dir.mkdir(parents=True, exist_ok=True)

    server_runner = ServerRunner()
    try:
        server_runner.start()
    except OSError as exc:
        log(f"Could not start server: {exc}")
        return

    config = load_config()
    hotkey = config["hotkey"]
    icon = build_tray_icon(hotkey, server_runner)

    log(f"Server running on {get_local_base_url(config)}")
    if config["sharing"]["lan_enabled"]:
        log(f"LAN sharing enabled at {get_lan_base_url(config)}")

    try:
        keyboard.add_hotkey(hotkey, lambda: capture_from_tray(icon))
        log(f"Press {hotkey} to capture a region.")
    except Exception as exc:
        log(f"Could not register hotkey {hotkey}: {exc}")

    log("App is running in the system tray.")
    icon.run()


if __name__ == "__main__":
    main()
