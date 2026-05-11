import tkinter as tk
import mss
import mss.tools
from datetime import datetime
import os
import pyperclip
import json

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
        self.on_capture_callback = on_capture_callback

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", self.cancel)
        self.root.bind_all("<Escape>", self.cancel)
        self.root.after(0, self.root.focus_force)

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
        self.root.destroy()
        
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
        self.root.unbind_all("<Escape>")
        self.root.destroy()

    def start(self):
        self.root.mainloop()

def capture_region(left, top, right, bottom):
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    save_dir = config.get('save_directory', 'screenshots')
    port = config.get('port', 8892)
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = os.path.join(save_dir, filename)
    
    with mss.mss() as sct:
        # mss uses {top, left, width, height}
        monitor = {"top": top, "left": left, "width": right - left, "height": bottom - top}
        sct_img = sct.grab(monitor)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)
        
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    url = f"http://{local_ip}:{port}/{filename}"
    pyperclip.copy(url)
    print(f"Captured: {filepath}")
    print(f"URL copied to clipboard: {url}")

def start_capture_ui():
    selector = RegionSelector(capture_region)
    selector.start()

if __name__ == "__main__":
    start_capture_ui()
