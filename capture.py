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
        self.root.attributes('-fullscreen', True)
        self.root.attributes("-topmost", True)
        self.root.config(cursor="cross")
        
        self.canvas = tk.Canvas(self.root, cursor="cross", bg="grey")
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
        
        # Ensure coordinates are in correct order (left, top, right, bottom)
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        right = max(self.start_x, end_x)
        bottom = max(self.start_y, end_y)
        
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
        
    url = f"http://127.0.0.1:{port}/{filename}"
    pyperclip.copy(url)
    print(f"Captured: {filepath}")
    print(f"URL copied to clipboard: {url}")

def start_capture_ui():
    selector = RegionSelector(capture_region)
    selector.start()

if __name__ == "__main__":
    start_capture_ui()