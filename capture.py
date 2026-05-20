import tkinter as tk
import threading
import keyboard
import mss
import mss.tools
from datetime import datetime
from pathlib import Path
import pyperclip

from config_manager import get_database_path, get_lan_base_url, get_local_base_url, load_config
from gallery_store import GalleryStore

class RegionSelector:
    def __init__(self, on_capture_callback):
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0.55)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        
        with mss.mss() as sct:
            all_monitors = sct.monitors[0]
            self.v_left = all_monitors["left"]
            self.v_top = all_monitors["top"]
            self.v_width = all_monitors["width"]
            self.v_height = all_monitors["height"]

        self.root.geometry(f"{self.v_width}x{self.v_height}+{self.v_left}+{self.v_top}")
        self.root.config(cursor="cross")
        
        self.canvas = tk.Canvas(self.root, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.start_x = None
        self.start_y = None
        self.cancelled = False
        self.selection_shadow = None
        self.selection_rect = None
        self.size_label_bg = None
        self.size_label = None
        self.closed = False
        self.cancel_requested = threading.Event()
        self.escape_hotkey = None
        self.on_capture_callback = on_capture_callback

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", self.cancel)
        self.root.bind_all("<Escape>", self.cancel)
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        self.install_escape_hotkey()
        self.root.after(0, self.focus_overlay)
        self.root.after(25, self.poll_cancel_request)

    def focus_overlay(self):
        if self.closed:
            return

        self.root.lift()
        self.root.focus_force()
        self.canvas.focus_set()

    def install_escape_hotkey(self):
        try:
            self.escape_hotkey = keyboard.add_hotkey("esc", self.request_cancel, suppress=False)
        except Exception as exc:
            print(f"Could not register Escape cancel hook: {exc}")

    def request_cancel(self):
        self.cancel_requested.set()

    def poll_cancel_request(self):
        if self.closed:
            return

        if self.cancel_requested.is_set():
            self.cancel()
            return

        self.root.after(25, self.poll_cancel_request)

    def on_button_press(self, event):
        if self.cancelled:
            return

        self.start_x = event.x
        self.start_y = event.y
        self.selection_shadow = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#000000",
            width=8
        )
        self.selection_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#ffff00",
            width=4,
            dash=(8, 4)
        )
        self.size_label_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill="#000000", outline="")
        self.size_label = self.canvas.create_text(
            0, 0,
            fill="#ffffff",
            anchor="nw",
            font=("Segoe UI", 11, "bold"),
            text="0 x 0"
        )

    def on_move_press(self, event):
        if self.cancelled or self.selection_rect is None:
            return

        cur_x, cur_y = (event.x, event.y)
        self.update_selection(cur_x, cur_y)

    def on_button_release(self, event):
        if self.cancelled or self.start_x is None or self.start_y is None:
            return

        end_x, end_y = (event.x, event.y)
        self.close()

        # Calculate absolute screen coordinates by adding the virtual screen offset
        abs_start_x = self.v_left + self.start_x
        abs_start_y = self.v_top + self.start_y
        abs_end_x = self.v_left + end_x
        abs_end_y = self.v_top + end_y

        left = min(abs_start_x, abs_end_x)
        top = min(abs_start_y, abs_end_y)
        right = max(abs_start_x, abs_end_x)
        bottom = max(abs_start_y, abs_end_y)
        
        if right - left > 0 and bottom - top > 0:
            self.on_capture_callback(left, top, right, bottom)

    def update_selection(self, cur_x, cur_y):
        self.canvas.coords(self.selection_shadow, self.start_x, self.start_y, cur_x, cur_y)
        self.canvas.coords(self.selection_rect, self.start_x, self.start_y, cur_x, cur_y)

        width = abs(cur_x - self.start_x)
        height = abs(cur_y - self.start_y)
        label_x = min(cur_x + 12, self.v_width - 100)
        label_y = min(cur_y + 12, self.v_height - 30)

        self.canvas.itemconfigure(self.size_label, text=f"{width} x {height}")
        self.canvas.coords(self.size_label, label_x + 8, label_y + 5)
        label_bbox = self.canvas.bbox(self.size_label)
        if label_bbox:
            self.canvas.coords(
                self.size_label_bg,
                label_bbox[0] - 8,
                label_bbox[1] - 5,
                label_bbox[2] + 8,
                label_bbox[3] + 5
            )
            self.canvas.tag_raise(self.size_label_bg)
            self.canvas.tag_raise(self.size_label)

    def cancel(self, event=None):
        self.cancelled = True
        self.close()

    def close(self):
        if self.closed:
            return

        self.closed = True
        self.root.unbind_all("<Escape>")
        if self.escape_hotkey is not None:
            try:
                keyboard.remove_hotkey(self.escape_hotkey)
            except Exception:
                pass
            self.escape_hotkey = None
        self.root.destroy()

    def start(self):
        self.root.mainloop()

def _capture_urls(config, capture):
    local_url = f"{get_local_base_url(config)}/captures/{capture['id']}/file"
    lan_url = None
    if capture.get("share_token"):
        lan_url = f"{get_lan_base_url(config)}/s/{capture['share_token']}"
    return local_url, lan_url


def _copy_to_clipboard(url):
    try:
        pyperclip.copy(url)
        return True
    except Exception as exc:
        print(f"Could not copy URL to clipboard: {exc}")
        return False


def capture_region(left, top, right, bottom):
    config = load_config()
    save_dir = Path(config["save_directory"])
    save_dir.mkdir(parents=True, exist_ok=True)
    store = GalleryStore(get_database_path(config))

    captured_at = datetime.now()
    filename = f"screenshot_{captured_at.strftime('%Y%m%d_%H%M%S_%f')}.png"
    filepath = save_dir / filename
    width = right - left
    height = bottom - top

    with mss.mss() as sct:
        # mss uses {top, left, width, height}
        monitor = {"top": top, "left": left, "width": width, "height": height}
        sct_img = sct.grab(monitor)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))

    capture = store.add_capture(
        filename=filename,
        path=filepath,
        width=width,
        height=height,
        file_size=filepath.stat().st_size,
        created_at=captured_at.isoformat(timespec="seconds"),
    )

    copy_preference = config["sharing"]["copy_after_capture"]
    if config["sharing"]["lan_enabled"] and copy_preference == "lan":
        capture = store.set_share_enabled(capture["id"], True) or capture

    local_url, lan_url = _capture_urls(config, capture)
    copied_url = None
    clipboard_copied = False
    if copy_preference == "lan" and lan_url:
        copied_url = lan_url
    elif copy_preference != "none":
        copied_url = local_url

    if copied_url:
        clipboard_copied = _copy_to_clipboard(copied_url)

    print(f"Captured: {filepath}")
    if copied_url:
        print(f"URL copied to clipboard: {copied_url}")

    result = dict(capture)
    result.update(
        {
            "local_url": local_url,
            "lan_url": lan_url,
            "copied_url": copied_url,
            "clipboard_copied": clipboard_copied,
        }
    )
    return result


def start_capture_ui(on_complete=None, on_error=None):
    def handle_capture(left, top, right, bottom):
        try:
            result = capture_region(left, top, right, bottom)
        except Exception as exc:
            if on_error:
                on_error(exc)
            else:
                print(f"Capture failed: {exc}")
            return

        if on_complete:
            on_complete(result)

    try:
        selector = RegionSelector(handle_capture)
        selector.start()
    except Exception as exc:
        if on_error:
            on_error(exc)
        else:
            print(f"Capture failed: {exc}")

if __name__ == "__main__":
    start_capture_ui()
