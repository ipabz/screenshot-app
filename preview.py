from __future__ import annotations

import ctypes
from io import BytesIO
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageTk
import pyperclip


CF_DIB = 8
GMEM_MOVEABLE = 0x0002
WINDOW_BG = "#f5f7fa"
SURFACE_BG = "#ffffff"
PREVIEW_BG = "#edf2f7"
BORDER = "#d8e0e8"
TEXT = "#17202a"
MUTED = "#5b6775"
PRIMARY = "#0f6f8f"
PRIMARY_HOVER = "#0c5f7a"
SECONDARY = "#ffffff"
SECONDARY_HOVER = "#f0f6f9"
SECONDARY_TEXT = "#1f3442"

try:
    USER32 = ctypes.WinDLL("user32", use_last_error=True)
    KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

    USER32.OpenClipboard.argtypes = [ctypes.c_void_p]
    USER32.OpenClipboard.restype = ctypes.c_bool
    USER32.EmptyClipboard.argtypes = []
    USER32.EmptyClipboard.restype = ctypes.c_bool
    USER32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    USER32.SetClipboardData.restype = ctypes.c_void_p
    USER32.CloseClipboard.argtypes = []
    USER32.CloseClipboard.restype = ctypes.c_bool

    KERNEL32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    KERNEL32.GlobalAlloc.restype = ctypes.c_void_p
    KERNEL32.GlobalLock.argtypes = [ctypes.c_void_p]
    KERNEL32.GlobalLock.restype = ctypes.c_void_p
    KERNEL32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    KERNEL32.GlobalUnlock.restype = ctypes.c_bool
    KERNEL32.GlobalFree.argtypes = [ctypes.c_void_p]
    KERNEL32.GlobalFree.restype = ctypes.c_void_p
except AttributeError:
    USER32 = None
    KERNEL32 = None


def _clipboard_error(message):
    error_code = ctypes.get_last_error()
    if error_code:
        raise OSError(error_code, message)
    raise RuntimeError(message)


def image_file_to_dib_bytes(image_path):
    with Image.open(image_path) as image:
        with BytesIO() as output:
            image.convert("RGB").save(output, "BMP")
            return output.getvalue()[14:]


def copy_image_to_clipboard(image_path):
    if USER32 is None or KERNEL32 is None:
        raise RuntimeError("Image clipboard copy is only supported on Windows.")

    dib_bytes = image_file_to_dib_bytes(image_path)
    handle = KERNEL32.GlobalAlloc(GMEM_MOVEABLE, len(dib_bytes))
    if not handle:
        _clipboard_error("Could not allocate clipboard memory.")

    locked_memory = KERNEL32.GlobalLock(handle)
    if not locked_memory:
        KERNEL32.GlobalFree(handle)
        _clipboard_error("Could not lock clipboard memory.")

    try:
        ctypes.memmove(locked_memory, dib_bytes, len(dib_bytes))
    finally:
        KERNEL32.GlobalUnlock(handle)

    if not USER32.OpenClipboard(None):
        KERNEL32.GlobalFree(handle)
        _clipboard_error("Could not open the clipboard.")

    try:
        if not USER32.EmptyClipboard():
            _clipboard_error("Could not clear the clipboard.")
        if not USER32.SetClipboardData(CF_DIB, handle):
            _clipboard_error("Could not copy the image to the clipboard.")
        handle = None
    finally:
        USER32.CloseClipboard()
        if handle is not None:
            KERNEL32.GlobalFree(handle)


def get_preview_url(capture_result):
    return capture_result.get("lan_url") or capture_result["local_url"]


class CapturePreview:
    def __init__(self, capture_result):
        self.capture_result = capture_result
        self.image_path = Path(capture_result["path"]).resolve()
        self.root = tk.Tk()
        self.root.title("Screenshot preview")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.configure(bg=WINDOW_BG)
        self.photo = None
        self.status_var = tk.StringVar(value="")

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.after(0, self.center)

    def build_ui(self):
        frame = tk.Frame(
            self.root,
            bg=SURFACE_BG,
            padx=18,
            pady=18,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        frame.grid(row=0, column=0, sticky="nsew")

        preview_image = self.load_preview_image()
        self.photo = ImageTk.PhotoImage(preview_image)

        image_label = tk.Label(frame, image=self.photo, bg=PREVIEW_BG, bd=0)
        image_label.grid(row=0, column=0, sticky="nsew")

        filename = self.capture_result["filename"]
        width = self.capture_result["width"]
        height = self.capture_result["height"]
        details = tk.Label(
            frame,
            text=f"{filename} - {width} x {height}",
            anchor="center",
            bg=SURFACE_BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        details.grid(row=1, column=0, sticky="ew", pady=(12, 10))

        actions = tk.Frame(frame, bg=SURFACE_BG)
        actions.grid(row=2, column=0, sticky="ew")

        self.create_action_button(
            actions,
            "Copy to clipboard",
            self.copy_image,
            primary=True,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.create_action_button(actions, "Copy image URL", self.copy_url).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        self.create_action_button(actions, "Copy image path", self.copy_path).grid(
            row=0, column=2, sticky="ew", padx=(6, 0)
        )

        for column in range(3):
            actions.columnconfigure(column, weight=1, uniform="actions")

        status = tk.Label(
            frame,
            textvariable=self.status_var,
            anchor="center",
            bg=SURFACE_BG,
            fg=MUTED,
            font=("Segoe UI", 9),
            height=1,
        )
        status.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        frame.columnconfigure(0, weight=1)

    def create_action_button(self, parent, text, command, primary=False):
        background = PRIMARY if primary else SECONDARY
        foreground = "#ffffff" if primary else SECONDARY_TEXT
        hover_background = PRIMARY_HOVER if primary else SECONDARY_HOVER
        border = PRIMARY if primary else BORDER

        wrapper = tk.Frame(parent, bg=border, padx=1, pady=1)
        button = tk.Button(
            wrapper,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=hover_background,
            activeforeground=foreground,
            relief="flat",
            bd=0,
            padx=14,
            pady=9,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            highlightthickness=1,
            highlightbackground=background,
            highlightcolor="#94d2bd",
            takefocus=True,
        )
        button.pack(fill="both", expand=True)
        button.bind("<Enter>", lambda _event: button.configure(bg=hover_background))
        button.bind("<Leave>", lambda _event: button.configure(bg=background))
        return wrapper

    def load_preview_image(self):
        with Image.open(self.image_path) as image:
            image = image.copy()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        max_width = min(820, int(screen_width * 0.65))
        max_height = min(520, int(screen_height * 0.55))
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        image.thumbnail((max_width, max_height), resample_filter)
        return image

    def copy_image(self):
        try:
            copy_image_to_clipboard(self.image_path)
        except Exception as exc:
            self.status_var.set(f"Could not copy image: {exc}")
            return

        self.finish("Copied image to clipboard")

    def copy_url(self):
        try:
            pyperclip.copy(get_preview_url(self.capture_result))
        except Exception as exc:
            self.status_var.set(f"Could not copy URL: {exc}")
            return

        self.finish("Copied image URL")

    def copy_path(self):
        try:
            pyperclip.copy(str(self.image_path))
        except Exception as exc:
            self.status_var.set(f"Could not copy path: {exc}")
            return

        self.finish("Copied image path")

    def finish(self, message):
        self.status_var.set(message)
        self.root.after(350, self.close)

    def center(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = max((self.root.winfo_screenwidth() - width) // 2, 0)
        y = max((self.root.winfo_screenheight() - height) // 2, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.lift()
        self.root.focus_force()

    def close(self):
        self.root.destroy()

    def start(self):
        self.root.mainloop()


def show_capture_preview(capture_result):
    CapturePreview(capture_result).start()
