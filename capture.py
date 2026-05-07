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
        self.root.attributes('-alpha', 0.3)  # Transparency
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True) # Remove window decorations
        
        # Get virtual screen dimensions (union of all monitors)
        with mss.mss() as sct:
            all_monitors = sct.monitors[0]
            self.v_left = all_monitors["left"]
            self.v_top = all_monitors["top"]
            self.v_width = all_monitors["width"]
            self.v_height = all_monitors["height"]

        # Set window geometry to cover all monitors
        self.root.geometry(f"{self.v_width}x{self.v_height}+{self.v_left}+{self.v_top}")
        self.root.config(cursor="cross")
        
        self.canvas = tk.Canvas(self.root, cursor="cross", bg="grey", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.on_capture_callback = on_capture_callback

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='red', width=2)

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
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