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
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((10, 14, 54, 48), radius=7, fill="#1f2937")
    draw.rounded_rectangle((15, 20, 49, 43), radius=4, outline="#facc15", width=4)
    draw.rectangle((27, 10, 37, 16), fill="#1f2937")
    draw.ellipse((29, 27, 35, 33), fill="#facc15")

    return image


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
