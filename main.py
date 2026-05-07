import json
import threading
import keyboard
import os
from server import run_server
from capture import start_capture_ui

def main():
    # Load configuration
    if not os.path.exists('config.json'):
        print("Config file not found. Please ensure config.json exists.")
        return

    with open('config.json', 'r') as f:
        config = json.load(f)

    port = config.get('port', 8892)
    hotkey = config.get('hotkey', 'ctrl+shift+s')
    save_dir = config.get('save_directory', 'screenshots')

    # Ensure save directory exists
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Start Flask server in a background thread
    print(f"Starting server on http://127.0.0.1:{port}")
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    # Register the global hotkey
    print(f"Press {hotkey} to capture a region.")
    keyboard.add_hotkey(hotkey, start_capture_ui)

    # Keep the main thread alive
    print("App is running. Press Ctrl+C to exit.")
    keyboard.wait()

if __name__ == "__main__":
    main()