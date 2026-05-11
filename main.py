import json
import threading
import keyboard
import os
import sys
from PIL import Image, ImageDraw
import pystray
from server import run_server
from capture import start_capture_ui

APP_NAME = "Screenshot App"


def log(message):
    if sys.stdout:
        print(message)


def load_config():
    if not os.path.exists('config.json'):
        log("Config file not found. Please ensure config.json exists.")
        return None

    with open('config.json', 'r') as f:
        return json.load(f)


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


def capture_from_tray():
    threading.Thread(target=start_capture_ui, daemon=True).start()


def quit_app(icon):
    keyboard.unhook_all()
    icon.stop()


def build_tray_icon(hotkey, port):
    menu = pystray.Menu(
        pystray.MenuItem("Capture now", lambda icon, item: capture_from_tray()),
        pystray.MenuItem(f"Hotkey: {hotkey}", None, enabled=False),
        pystray.MenuItem(f"Server: http://127.0.0.1:{port}", None, enabled=False),
        pystray.MenuItem("Quit", lambda icon, item: quit_app(icon)),
    )

    return pystray.Icon(APP_NAME, create_tray_image(), APP_NAME, menu)


def main():
    config = load_config()
    if config is None:
        return

    port = config.get('port', 8892)
    hotkey = config.get('hotkey', 'ctrl+shift+s')
    save_dir = config.get('save_directory', 'screenshots')

    # Ensure save directory exists
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Start Flask server in a background thread
    log(f"Starting server on http://127.0.0.1:{port}")
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    # Register the global hotkey
    log(f"Press {hotkey} to capture a region.")
    keyboard.add_hotkey(hotkey, start_capture_ui)

    # Keep the app alive through the Windows notification-area icon.
    log("App is running in the system tray.")
    icon = build_tray_icon(hotkey, port)
    icon.run()

if __name__ == "__main__":
    main()
