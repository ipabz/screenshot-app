from __future__ import annotations

import ctypes
import math
from io import BytesIO
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk
import pyperclip


CF_DIB = 8
GMEM_MOVEABLE = 0x0002
WINDOW_BG = "#f5f7fa"
SURFACE_BG = "#ffffff"
PREVIEW_BG = "#edf2f7"
BORDER = "#d8e0e8"
TEXT = "#17202a"
MUTED = "#5b6775"
SUCCESS = "#0f766e"
ERROR = "#9b1c31"
PRIMARY = "#0f6f8f"
PRIMARY_HOVER = "#0c5f7a"
SECONDARY = "#ffffff"
SECONDARY_HOVER = "#f0f6f9"
SECONDARY_TEXT = "#1f3442"
MIN_WINDOW_WIDTH = 720
MIN_WINDOW_HEIGHT = 460
ANNOTATION_WIDTH = 5
ANNOTATION_TOOLS = {
    "pen": "Pen",
    "rectangle": "Box",
    "arrow": "Arrow",
}
ANNOTATION_COLORS = ["#ef4444", "#f59e0b", "#2563eb", "#111827"]

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


def image_to_dib_bytes(image):
    with BytesIO() as output:
        image.convert("RGB").save(output, "BMP")
        return output.getvalue()[14:]


def image_file_to_dib_bytes(image_path):
    with Image.open(image_path) as image:
        return image_to_dib_bytes(image)


def copy_image_to_clipboard(image_source):
    if USER32 is None or KERNEL32 is None:
        raise RuntimeError("Image clipboard copy is only supported on Windows.")

    if isinstance(image_source, Image.Image):
        dib_bytes = image_to_dib_bytes(image_source)
    else:
        dib_bytes = image_file_to_dib_bytes(image_source)

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


def format_file_size(value):
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / 1024 / 1024:.1f} MB"


def fit_image_size(image_size, max_size):
    image_width, image_height = image_size
    max_width, max_height = max_size
    if image_width <= 0 or image_height <= 0 or max_width <= 0 or max_height <= 0:
        return 1, 1

    scale = min(max_width / image_width, max_height / image_height)
    return max(1, int(image_width * scale)), max(1, int(image_height * scale))


def draw_arrow(draw, start, end, color, width):
    draw.line([start, end], fill=color, width=width)

    start_x, start_y = start
    end_x, end_y = end
    angle = math.atan2(end_y - start_y, end_x - start_x)
    arrow_size = max(width * 4, 14)
    left = (
        end_x - arrow_size * math.cos(angle - math.pi / 6),
        end_y - arrow_size * math.sin(angle - math.pi / 6),
    )
    right = (
        end_x - arrow_size * math.cos(angle + math.pi / 6),
        end_y - arrow_size * math.sin(angle + math.pi / 6),
    )
    draw.polygon([end, left, right], fill=color)


def draw_annotation(draw, annotation):
    tool = annotation["tool"]
    color = annotation["color"]
    width = annotation["width"]

    if tool == "pen":
        points = annotation["points"]
        if len(points) > 1:
            draw.line(points, fill=color, width=width, joint="curve")
        return

    start = annotation["start"]
    end = annotation["end"]
    if tool == "rectangle":
        left = min(start[0], end[0])
        top = min(start[1], end[1])
        right = max(start[0], end[0])
        bottom = max(start[1], end[1])
        draw.rectangle([left, top, right, bottom], outline=color, width=width)
    elif tool == "arrow":
        draw_arrow(draw, start, end, color, width)


def render_annotations(image, annotations):
    output = image.copy()
    draw = ImageDraw.Draw(output)
    for annotation in annotations:
        draw_annotation(draw, annotation)
    return output


class CapturePreview:
    def __init__(self, capture_result):
        self.capture_result = capture_result
        self.image_path = Path(capture_result["path"]).resolve()
        self.original_image = self.load_original_image()
        self.root = tk.Tk()
        self.root.title("Screenshot preview")
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.root.configure(bg=WINDOW_BG)
        self.photo = None
        self.preview_canvas = None
        self.resize_after_id = None
        self.status_var = tk.StringVar(value="")
        self.status_label = None
        self.annotations = []
        self.current_annotation = None
        self.active_tool = "pen"
        self.active_color = ANNOTATION_COLORS[0]
        self.tool_buttons = {}
        self.color_buttons = {}
        self.image_origin = (0, 0)
        self.display_size = (1, 1)
        self.display_scale = 1.0

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.after(0, self.center)

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = tk.Frame(self.root, bg=WINDOW_BG, padx=16, pady=16)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        self.build_header(shell)
        self.build_annotation_bar(shell)
        self.build_preview_area(shell)
        self.build_action_bar(shell)

    def build_header(self, parent):
        header = tk.Frame(parent, bg=WINDOW_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)

        title = tk.Label(
            header,
            text="Screenshot captured",
            bg=WINDOW_BG,
            fg=TEXT,
            anchor="w",
            font=("Segoe UI", 13, "bold"),
        )
        title.grid(row=0, column=0, sticky="ew")

        filename = self.capture_result["filename"]
        width = self.capture_result["width"]
        height = self.capture_result["height"]
        file_size = format_file_size(self.capture_result["file_size"])
        details = tk.Label(
            header,
            text=f"{filename}   {width} x {height}   {file_size}",
            bg=WINDOW_BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        )
        details.grid(row=1, column=0, sticky="ew", pady=(3, 0))

    def build_annotation_bar(self, parent):
        bar = tk.Frame(parent, bg=WINDOW_BG)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        bar.columnconfigure(8, weight=1)

        label = tk.Label(
            bar,
            text="Annotate",
            bg=WINDOW_BG,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        label.grid(row=0, column=0, sticky="w", padx=(0, 8))

        column = 1
        for tool, text in ANNOTATION_TOOLS.items():
            button = self.create_toolbar_button(
                bar,
                text,
                lambda selected_tool=tool: self.set_active_tool(selected_tool),
            )
            button.grid(row=0, column=column, padx=(0, 6))
            self.tool_buttons[tool] = button
            column += 1

        swatch_group = tk.Frame(bar, bg=WINDOW_BG)
        swatch_group.grid(row=0, column=column, padx=(4, 8))
        for index, color in enumerate(ANNOTATION_COLORS):
            swatch = tk.Button(
                swatch_group,
                bg=color,
                activebackground=color,
                relief="flat",
                bd=0,
                width=2,
                height=1,
                cursor="hand2",
                command=lambda selected_color=color: self.set_active_color(selected_color),
                takefocus=True,
            )
            swatch.grid(row=0, column=index, padx=(0, 5))
            self.color_buttons[color] = swatch

        column += 1
        self.create_toolbar_button(bar, "Undo", self.undo_annotation).grid(
            row=0, column=column, padx=(0, 6)
        )
        self.create_toolbar_button(bar, "Clear", self.clear_annotations).grid(
            row=0, column=column + 1
        )
        self.refresh_annotation_controls()

    def build_preview_area(self, parent):
        frame = tk.Frame(
            parent,
            bg=SURFACE_BG,
            padx=12,
            pady=12,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        frame.grid(row=2, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        image_border = tk.Frame(frame, bg=BORDER, padx=1, pady=1)
        image_border.grid(row=0, column=0, sticky="nsew")
        image_border.columnconfigure(0, weight=1)
        image_border.rowconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(
            image_border,
            bg=PREVIEW_BG,
            bd=0,
            highlightthickness=0,
            cursor="crosshair",
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self.schedule_preview_resize)
        self.preview_canvas.bind("<ButtonPress-1>", self.start_annotation)
        self.preview_canvas.bind("<B1-Motion>", self.update_annotation)
        self.preview_canvas.bind("<ButtonRelease-1>", self.finish_annotation)

    def build_action_bar(self, parent):
        action_bar = tk.Frame(parent, bg=WINDOW_BG)
        action_bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        action_bar.columnconfigure(0, weight=1)

        self.status_label = tk.Label(
            action_bar,
            textvariable=self.status_var,
            anchor="w",
            bg=WINDOW_BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        actions = tk.Frame(action_bar, bg=WINDOW_BG)
        actions.grid(row=0, column=1, sticky="e")

        self.create_action_button(
            actions,
            "Copy to clipboard",
            self.copy_image,
            primary=True,
        ).grid(row=0, column=0, padx=(0, 8))
        self.create_action_button(actions, "Copy image URL", self.copy_url).grid(
            row=0, column=1, padx=(0, 8)
        )
        self.create_action_button(actions, "Copy image path", self.copy_path).grid(
            row=0, column=2
        )

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
            width=18,
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

    def create_toolbar_button(self, parent, text, command):
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=SECONDARY,
            fg=SECONDARY_TEXT,
            activebackground=SECONDARY_HOVER,
            activeforeground=SECONDARY_TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor="#94d2bd",
            takefocus=True,
        )
        return button

    def set_active_tool(self, tool):
        self.active_tool = tool
        self.refresh_annotation_controls()

    def set_active_color(self, color):
        self.active_color = color
        self.refresh_annotation_controls()

    def refresh_annotation_controls(self):
        for tool, button in self.tool_buttons.items():
            if tool == self.active_tool:
                button.configure(bg=PRIMARY, fg="#ffffff", activebackground=PRIMARY_HOVER)
            else:
                button.configure(bg=SECONDARY, fg=SECONDARY_TEXT, activebackground=SECONDARY_HOVER)

        for color, button in self.color_buttons.items():
            button.configure(
                highlightthickness=2 if color == self.active_color else 1,
                highlightbackground=TEXT if color == self.active_color else BORDER,
            )

    def undo_annotation(self):
        if self.annotations:
            self.annotations.pop()
            self.set_status("Removed last annotation")
            self.redraw_preview()

    def clear_annotations(self):
        if self.annotations:
            self.annotations.clear()
            self.current_annotation = None
            self.set_status("Cleared annotations")
            self.redraw_preview()

    def load_original_image(self):
        with Image.open(self.image_path) as image:
            return image.copy()

    def get_initial_preview_bounds(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        return min(820, int(screen_width * 0.65)), min(520, int(screen_height * 0.55))

    def get_preview_image(self, max_size=None):
        if max_size is None:
            max_size = self.get_initial_preview_bounds()

        target_size = fit_image_size(self.original_image.size, max_size)
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        return self.original_image.resize(target_size, resample_filter)

    def schedule_preview_resize(self, event):
        if self.resize_after_id is not None:
            self.root.after_cancel(self.resize_after_id)
        self.resize_after_id = self.root.after(60, lambda: self.resize_preview(event.width, event.height))

    def resize_preview(self, max_width, max_height):
        self.resize_after_id = None
        if self.preview_canvas is None or max_width <= 1 or max_height <= 1:
            return

        preview_image = self.get_preview_image((max_width, max_height))
        self.display_size = preview_image.size
        self.display_scale = self.display_size[0] / self.original_image.size[0]
        self.image_origin = (
            max((max_width - self.display_size[0]) // 2, 0),
            max((max_height - self.display_size[1]) // 2, 0),
        )
        self.photo = ImageTk.PhotoImage(preview_image)
        self.redraw_preview()

    def redraw_preview(self):
        if self.preview_canvas is None or self.photo is None:
            return

        self.preview_canvas.delete("all")
        origin_x, origin_y = self.image_origin
        self.preview_canvas.create_image(origin_x, origin_y, image=self.photo, anchor="nw")
        for annotation in [*self.annotations, self.current_annotation]:
            if annotation is not None:
                self.draw_canvas_annotation(annotation)

    def draw_canvas_annotation(self, annotation):
        tool = annotation["tool"]
        color = annotation["color"]
        width = max(2, int(annotation["width"] * self.display_scale))

        if tool == "pen":
            points = [self.image_to_canvas_point(point) for point in annotation["points"]]
            if len(points) > 1:
                coords = [coord for point in points for coord in point]
                self.preview_canvas.create_line(*coords, fill=color, width=width, smooth=True)
            return

        start = self.image_to_canvas_point(annotation["start"])
        end = self.image_to_canvas_point(annotation["end"])
        if tool == "rectangle":
            self.preview_canvas.create_rectangle(*start, *end, outline=color, width=width)
        elif tool == "arrow":
            self.preview_canvas.create_line(*start, *end, fill=color, width=width, arrow=tk.LAST)

    def image_to_canvas_point(self, point):
        origin_x, origin_y = self.image_origin
        return (
            origin_x + point[0] * self.display_scale,
            origin_y + point[1] * self.display_scale,
        )

    def canvas_to_image_point(self, x, y):
        origin_x, origin_y = self.image_origin
        image_x = (x - origin_x) / self.display_scale
        image_y = (y - origin_y) / self.display_scale
        if image_x < 0 or image_y < 0:
            return None
        if image_x > self.original_image.size[0] or image_y > self.original_image.size[1]:
            return None
        return (
            min(max(image_x, 0), self.original_image.size[0] - 1),
            min(max(image_y, 0), self.original_image.size[1] - 1),
        )

    def start_annotation(self, event):
        point = self.canvas_to_image_point(event.x, event.y)
        if point is None:
            self.current_annotation = None
            return

        if self.active_tool == "pen":
            self.current_annotation = self.new_annotation(points=[point])
        else:
            self.current_annotation = self.new_annotation(start=point, end=point)

    def update_annotation(self, event):
        if self.current_annotation is None:
            return

        point = self.canvas_to_image_point(event.x, event.y)
        if point is None:
            return

        if self.current_annotation["tool"] == "pen":
            self.current_annotation["points"].append(point)
        else:
            self.current_annotation["end"] = point
        self.redraw_preview()

    def finish_annotation(self, event):
        if self.current_annotation is None:
            return

        self.update_annotation(event)
        if self.annotation_has_size(self.current_annotation):
            self.annotations.append(self.current_annotation)
            self.set_status("Annotation added")
        self.current_annotation = None
        self.redraw_preview()

    def new_annotation(self, **values):
        annotation = {
            "tool": self.active_tool,
            "color": self.active_color,
            "width": ANNOTATION_WIDTH,
        }
        annotation.update(values)
        return annotation

    def annotation_has_size(self, annotation):
        if annotation["tool"] == "pen":
            return len(annotation["points"]) > 1

        start = annotation["start"]
        end = annotation["end"]
        return abs(start[0] - end[0]) > 2 or abs(start[1] - end[1]) > 2

    def get_output_image(self):
        return render_annotations(self.original_image, self.annotations)

    def save_output_image(self):
        output = self.get_output_image()
        output.save(self.image_path)
        self.capture_result["file_size"] = self.image_path.stat().st_size

    def copy_image(self):
        try:
            copy_image_to_clipboard(self.get_output_image())
        except Exception as exc:
            self.set_status(f"Could not copy image: {exc}", error=True)
            return

        self.finish("Copied image to clipboard")

    def copy_url(self):
        try:
            self.save_output_image()
            pyperclip.copy(get_preview_url(self.capture_result))
        except Exception as exc:
            self.set_status(f"Could not copy URL: {exc}", error=True)
            return

        self.finish("Copied image URL")

    def copy_path(self):
        try:
            self.save_output_image()
            pyperclip.copy(str(self.image_path))
        except Exception as exc:
            self.set_status(f"Could not copy path: {exc}", error=True)
            return

        self.finish("Copied image path")

    def set_status(self, message, success=False, error=False):
        if self.status_label is not None:
            if error:
                self.status_label.configure(fg=ERROR)
            elif success:
                self.status_label.configure(fg=SUCCESS)
            else:
                self.status_label.configure(fg=MUTED)
        self.status_var.set(message)

    def finish(self, message):
        self.set_status(message, success=True)

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
