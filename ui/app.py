from __future__ import annotations

import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional

import customtkinter as ctk

from converter.handlers import FormatHandlerRegistry
from converter.models import (
    ConversionConfig,
    FileResult,
    OutputFormat,
    OutputMode,
    ResizeConfig,
    ResizeMode,
)
from converter.optional_deps import get_missing_info
from converter.processor import BatchProcessor

_ALL_KNOWN_EXTS = {
    ".jpg", ".jpeg", ".jfif", ".jpe", ".png", ".webp", ".bmp",
    ".gif", ".tiff", ".tif", ".ico", ".heic", ".heif", ".avif",
}

_FORMAT_NAMES: Dict[str, str] = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".jfif": "JPEG", ".jpe": "JPEG",
    ".png": "PNG", ".webp": "WebP", ".bmp": "BMP", ".gif": "GIF",
    ".tiff": "TIFF", ".tif": "TIFF", ".ico": "ICO",
    ".heic": "HEIC", ".heif": "HEIF", ".avif": "AVIF",
}

_UNSUPPORTED_HINTS: Dict[str, str] = {
    ".heic": "pip install pillow-heif",
    ".heif": "pip install pillow-heif",
    ".avif": "pip install pillow-avif-plugin",
}

_STATUS_TEXT: Dict[str, str] = {
    "pending":     "Pending",
    "unsupported": "⚠ Unsupported",
    "converting":  "… Converting",
    "success":     "✓ Done",
    "error":       "✗ Error",
}

_STATUS_COLOR: Dict[str, tuple[str, str]] = {
    "pending":     ("gray50", "gray60"),
    "unsupported": ("orange", "orange"),
    "converting":  ("dodger blue", "dodger blue"),
    "success":     ("green3", "light green"),
    "error":       ("red3", "tomato"),
}


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _int_or_none(s: str) -> Optional[int]:
    try:
        v = int(s.strip())
        return v if v > 0 else None
    except ValueError:
        return None


class _Tooltip:
    def __init__(self, widget: ctk.CTkBaseClass, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: Optional[ctk.CTkToplevel] = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + 20
        self._tip = ctk.CTkToplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.geometry(f"+{x}+{y}")
        ctk.CTkLabel(self._tip, text=self._text, wraplength=300).pack(padx=8, pady=4)

    def _hide(self, _event=None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


class App(ctk.CTk):
    def __init__(self, registry: FormatHandlerRegistry, deps: Dict[str, bool]) -> None:
        super().__init__()
        self._registry = registry
        self._deps = deps
        self._processor = BatchProcessor(registry)
        self._converting = False

        # file list state: list of dicts with keys: path, status, status_detail, fmt, size_str
        self._files: List[Dict] = []
        # parallel list of row-widget dicts
        self._rows: List[Dict] = []

        self._setup_vars()
        self._setup_window()
        self._build_ui()
        self._show_missing_deps_banner()

    # ------------------------------------------------------------------ setup

    def _setup_vars(self) -> None:
        self._format_var = ctk.StringVar(value="jpg")
        self._quality_var = ctk.IntVar(value=85)
        self._compression_var = ctk.IntVar(value=6)
        self._resize_var = ctk.StringVar(value=ResizeMode.NONE.value)
        self._width_var = ctk.StringVar()
        self._height_var = ctk.StringVar()
        self._output_mode_var = ctk.StringVar(value=OutputMode.FOLDER.value)
        self._folder_var = ctk.StringVar()
        self._suffix_var = ctk.StringVar(value="_converted")
        self._recursive_var = ctk.BooleanVar(value=False)
        self._exif_var = ctk.BooleanVar(value=False)

    def _setup_window(self) -> None:
        self.title("Bulk Image Converter")
        self.geometry("980x900")
        self.minsize(820, 720)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    # ------------------------------------------------------------------ ui build

    def _build_ui(self) -> None:
        outer = ctk.CTkScrollableFrame(self, label_text="")
        outer.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        outer.grid_columnconfigure(0, weight=1)

        self._build_file_section(outer)
        self._build_middle_row(outer)
        self._build_output_section(outer)
        self._build_action_section(outer)
        self._build_log_section(outer)

    def _section(self, parent: ctk.CTkFrame, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent)
        frame.grid(sticky="ew", padx=10, pady=(6, 0))
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4)
        )
        return frame

    # ------------------------------------------------------------------ file section

    def _build_file_section(self, parent: ctk.CTkFrame) -> None:
        sec = self._section(parent, "File Input")

        ctrl_row = ctk.CTkFrame(sec, fg_color="transparent")
        ctrl_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))

        ctk.CTkButton(ctrl_row, text="Add Files", width=100, command=self._add_files).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(ctrl_row, text="Add Folder", width=110, command=self._add_folder).pack(
            side="left", padx=(0, 6)
        )
        self._recursive_cb = ctk.CTkCheckBox(
            ctrl_row, text="Recursive", variable=self._recursive_var, width=100
        )
        self._recursive_cb.pack(side="left", padx=(0, 12))
        ctk.CTkButton(
            ctrl_row, text="Clear List", width=90, fg_color="gray40",
            hover_color="gray30", command=self._clear_list
        ).pack(side="right")

        self._build_file_list(sec)
        self._build_badges(sec)

    def _build_file_list(self, parent: ctk.CTkFrame) -> None:
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 2))
        for col, (txt, w) in enumerate([("Filename", 300), ("Format", 70), ("Size", 80), ("Status", 180)]):
            ctk.CTkLabel(hdr, text=txt, width=w, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=col, sticky="w", padx=4)

        self._file_scroll = ctk.CTkScrollableFrame(parent, height=160)
        self._file_scroll.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 4))
        self._file_scroll.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(
            self._file_scroll, text="No files added yet. Click 'Add Files' or 'Add Folder'.",
            text_color="gray50"
        )
        self._empty_label.grid(row=0, column=0, pady=20)

    def _build_badges(self, parent: ctk.CTkFrame) -> None:
        badge_row = ctk.CTkFrame(parent, fg_color="transparent")
        badge_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctk.CTkLabel(badge_row, text="Optional formats:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))

        badges = [
            ("HEIC/HEIF", self._deps.get("heif", False), "pip install pillow-heif"),
            ("AVIF",      self._deps.get("avif", False),  "pip install pillow-avif-plugin"),
        ]
        for name, ok, hint in badges:
            color = ("green3", "light green") if ok else ("gray50", "gray60")
            icon = " ✓" if ok else " ✗"
            lbl = ctk.CTkLabel(badge_row, text=f"{name}{icon}", text_color=color,
                               font=ctk.CTkFont(size=11))
            lbl.pack(side="left", padx=6)
            if not ok:
                _Tooltip(lbl, f"Not available — {hint}")

    # ------------------------------------------------------------------ settings (middle row)

    def _build_middle_row(self, parent: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(sticky="ew", padx=10, pady=(6, 0))
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)
        self._build_conversion_section(row)
        self._build_resize_section(row)

    def _build_conversion_section(self, parent: ctk.CTkFrame) -> None:
        sec = ctk.CTkFrame(parent)
        sec.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        sec.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(sec, text="Conversion Settings", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4)
        )

        fmt_row = ctk.CTkFrame(sec, fg_color="transparent")
        fmt_row.grid(row=1, column=0, sticky="ew", padx=10)
        ctk.CTkLabel(fmt_row, text="Output format:").pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(fmt_row, text="JPG", variable=self._format_var, value="jpg",
                           command=self._update_format_ui).pack(side="left", padx=4)
        ctk.CTkRadioButton(fmt_row, text="PNG", variable=self._format_var, value="png",
                           command=self._update_format_ui).pack(side="left", padx=4)

        self._quality_frame = ctk.CTkFrame(sec, fg_color="transparent")
        self._quality_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 0))
        ctk.CTkLabel(self._quality_frame, text="JPEG Quality:").pack(side="left", padx=(0, 6))
        self._quality_slider = ctk.CTkSlider(
            self._quality_frame, from_=1, to=95, number_of_steps=94,
            variable=self._quality_var, command=lambda v: self._quality_lbl.configure(text=f"{int(v)}")
        )
        self._quality_slider.pack(side="left", expand=True, fill="x")
        self._quality_lbl = ctk.CTkLabel(self._quality_frame, text="85", width=32)
        self._quality_lbl.pack(side="left", padx=(4, 0))

        self._comp_frame = ctk.CTkFrame(sec, fg_color="transparent")
        self._comp_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(6, 8))
        ctk.CTkLabel(self._comp_frame, text="PNG Compression:").pack(side="left", padx=(0, 6))
        self._comp_slider = ctk.CTkSlider(
            self._comp_frame, from_=0, to=9, number_of_steps=9,
            variable=self._compression_var, command=lambda v: self._comp_lbl.configure(text=f"{int(v)}")
        )
        self._comp_slider.pack(side="left", expand=True, fill="x")
        self._comp_lbl = ctk.CTkLabel(self._comp_frame, text="6", width=32)
        self._comp_lbl.pack(side="left", padx=(4, 0))

        self._update_format_ui()

    def _build_resize_section(self, parent: ctk.CTkFrame) -> None:
        sec = ctk.CTkFrame(parent)
        sec.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        sec.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(sec, text="Resize Settings", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 4)
        )

        mode_row = ctk.CTkFrame(sec, fg_color="transparent")
        mode_row.grid(row=1, column=0, sticky="ew", padx=10)
        ctk.CTkLabel(mode_row, text="Mode:").pack(side="left", padx=(0, 8))
        self._resize_menu = ctk.CTkOptionMenu(
            mode_row, values=[m.value for m in ResizeMode],
            variable=self._resize_var, command=lambda _: self._update_resize_ui()
        )
        self._resize_menu.pack(side="left")

        dim_row = ctk.CTkFrame(sec, fg_color="transparent")
        dim_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 0))
        ctk.CTkLabel(dim_row, text="W:").pack(side="left")
        self._width_entry = ctk.CTkEntry(dim_row, textvariable=self._width_var, width=70,
                                         placeholder_text="px")
        self._width_entry.pack(side="left", padx=(2, 8))
        ctk.CTkLabel(dim_row, text="H:").pack(side="left")
        self._height_entry = ctk.CTkEntry(dim_row, textvariable=self._height_var, width=70,
                                           placeholder_text="px")
        self._height_entry.pack(side="left", padx=(2, 0))

        self._stretch_warn = ctk.CTkLabel(sec, text="⚠ Stretch distorts aspect ratio",
                                           text_color="red")
        self._stretch_warn.grid(row=3, column=0, sticky="w", padx=10, pady=(4, 8))

        self._update_resize_ui()

    # ------------------------------------------------------------------ output section

    def _build_output_section(self, parent: ctk.CTkFrame) -> None:
        sec = self._section(parent, "Output Settings")

        mode_row = ctk.CTkFrame(sec, fg_color="transparent")
        mode_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        ctk.CTkLabel(mode_row, text="Save to:").pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(mode_row, text="Output Folder", variable=self._output_mode_var,
                           value=OutputMode.FOLDER.value,
                           command=self._update_output_ui).pack(side="left", padx=4)
        ctk.CTkRadioButton(mode_row, text="Alongside Source", variable=self._output_mode_var,
                           value=OutputMode.ALONGSIDE.value,
                           command=self._update_output_ui).pack(side="left", padx=4)

        self._folder_frame = ctk.CTkFrame(sec, fg_color="transparent")
        self._folder_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkLabel(self._folder_frame, text="Folder:").pack(side="left", padx=(0, 6))
        self._folder_entry = ctk.CTkEntry(self._folder_frame, textvariable=self._folder_var,
                                           width=400, placeholder_text="Select output folder…")
        self._folder_entry.pack(side="left", expand=True, fill="x")
        ctk.CTkButton(self._folder_frame, text="Browse…", width=80,
                      command=self._browse_folder).pack(side="left", padx=(6, 0))

        self._suffix_frame = ctk.CTkFrame(sec, fg_color="transparent")
        self._suffix_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkLabel(self._suffix_frame, text="Filename suffix:").pack(side="left", padx=(0, 6))
        self._suffix_entry = ctk.CTkEntry(self._suffix_frame, textvariable=self._suffix_var, width=160)
        self._suffix_entry.pack(side="left")

        exif_row = ctk.CTkFrame(sec, fg_color="transparent")
        exif_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctk.CTkCheckBox(exif_row, text="Preserve EXIF metadata", variable=self._exif_var).pack(side="left")

        self._update_output_ui()

    # ------------------------------------------------------------------ action section

    def _build_action_section(self, parent: ctk.CTkFrame) -> None:
        sec = self._section(parent, "Convert")

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        self._convert_btn = ctk.CTkButton(
            btn_row, text="Convert", width=140, height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_conversion, state="disabled"
        )
        self._convert_btn.pack(side="left", padx=(0, 12))
        self._status_lbl = ctk.CTkLabel(btn_row, text="Add files to begin.", text_color="gray60")
        self._status_lbl.pack(side="left")

        self._progress_bar = ctk.CTkProgressBar(sec, height=14)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

    # ------------------------------------------------------------------ log section

    def _build_log_section(self, parent: ctk.CTkFrame) -> None:
        sec = self._section(parent, "Conversion Log")

        self._log_box = ctk.CTkTextbox(sec, height=180, font=ctk.CTkFont(family="Courier", size=11))
        self._log_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctk.CTkButton(btn_row, text="Copy Log", width=100, command=self._copy_log).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Export Log…", width=110, command=self._export_log).pack(side="left")

    # ------------------------------------------------------------------ file management

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[("Image files", " ".join(f"*{e}" for e in sorted(_ALL_KNOWN_EXTS))),
                       ("All files", "*.*")]
        )
        for p in paths:
            self._register_file(Path(p))
        self._update_convert_button()

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder containing images")
        if not folder:
            return
        root_path = Path(folder)
        recursive = self._recursive_var.get()
        files: List[Path] = []
        if recursive:
            for dirpath, _dirs, filenames in os.walk(root_path):
                for f in filenames:
                    p = Path(dirpath) / f
                    if p.suffix.lower() in _ALL_KNOWN_EXTS:
                        files.append(p)
        else:
            files = [p for p in root_path.iterdir()
                     if p.is_file() and p.suffix.lower() in _ALL_KNOWN_EXTS]
        files.sort()
        for p in files:
            self._register_file(p)
        self._update_convert_button()

    def _register_file(self, path: Path) -> None:
        # Skip exact duplicates
        existing = {e["path"] for e in self._files}
        if path in existing:
            return

        ext = path.suffix.lower()
        supported = ext in self._registry.available_extensions

        if supported:
            status = "pending"
            status_detail = ""
        elif ext in _UNSUPPORTED_HINTS:
            status = "unsupported"
            status_detail = f"Unsupported — {_UNSUPPORTED_HINTS[ext]}"
        else:
            status = "unsupported"
            status_detail = "Format not supported"

        try:
            size_str = _fmt_size(float(path.stat().st_size))
        except OSError:
            size_str = "?"

        entry = {
            "path": path,
            "status": status,
            "status_detail": status_detail,
            "fmt": _FORMAT_NAMES.get(ext, ext.lstrip(".").upper()),
            "size_str": size_str,
        }
        self._files.append(entry)
        self._add_file_row(entry)

    def _add_file_row(self, entry: Dict) -> None:
        if self._empty_label.winfo_exists():
            self._empty_label.grid_remove()

        idx = len(self._rows)
        row_frame = ctk.CTkFrame(self._file_scroll, fg_color="transparent")
        row_frame.grid(row=idx, column=0, sticky="ew", pady=1)

        name_lbl = ctk.CTkLabel(row_frame, text=entry["path"].name, width=300, anchor="w",
                                 font=ctk.CTkFont(size=11))
        name_lbl.grid(row=0, column=0, sticky="w", padx=4)

        fmt_lbl = ctk.CTkLabel(row_frame, text=entry["fmt"], width=70, anchor="w",
                               font=ctk.CTkFont(size=11))
        fmt_lbl.grid(row=0, column=1, sticky="w", padx=4)

        size_lbl = ctk.CTkLabel(row_frame, text=entry["size_str"], width=80, anchor="w",
                                font=ctk.CTkFont(size=11))
        size_lbl.grid(row=0, column=2, sticky="w", padx=4)

        status_text = _STATUS_TEXT[entry["status"]]
        if entry["status"] == "unsupported":
            status_text = entry["status_detail"] or status_text
        status_lbl = ctk.CTkLabel(
            row_frame, text=status_text, width=220, anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=_STATUS_COLOR[entry["status"]]
        )
        status_lbl.grid(row=0, column=3, sticky="w", padx=4)

        if entry["status"] == "unsupported" and entry["status_detail"]:
            _Tooltip(status_lbl, entry["status_detail"])

        self._rows.append({"frame": row_frame, "status_lbl": status_lbl})

    def _clear_list(self) -> None:
        if self._converting:
            return
        for row in self._rows:
            row["frame"].destroy()
        self._files.clear()
        self._rows.clear()
        self._empty_label.grid()
        self._progress_bar.set(0)
        self._status_lbl.configure(text="Add files to begin.")
        self._update_convert_button()

    # ------------------------------------------------------------------ ui state updates

    def _update_format_ui(self) -> None:
        is_jpg = self._format_var.get() == "jpg"
        if is_jpg:
            self._quality_frame.grid()
            self._comp_frame.grid_remove()
        else:
            self._quality_frame.grid_remove()
            self._comp_frame.grid()

    def _update_resize_ui(self) -> None:
        mode_str = self._resize_var.get()
        active = mode_str != ResizeMode.NONE.value
        state = "normal" if active else "disabled"
        self._width_entry.configure(state=state)
        self._height_entry.configure(state=state)
        if mode_str == ResizeMode.STRETCH.value:
            self._stretch_warn.grid()
        else:
            self._stretch_warn.grid_remove()

    def _update_output_ui(self) -> None:
        is_folder = self._output_mode_var.get() == OutputMode.FOLDER.value
        if is_folder:
            self._folder_frame.grid()
            self._suffix_frame.grid_remove()
        else:
            self._folder_frame.grid_remove()
            self._suffix_frame.grid()
        self._update_convert_button()

    def _update_convert_button(self) -> None:
        if not hasattr(self, "_convert_btn"):
            return
        if self._converting:
            self._convert_btn.configure(state="disabled")
            return
        has_valid = any(e["status"] == "pending" for e in self._files)
        output_ok = self._check_output_ready()
        state = "normal" if (has_valid and output_ok) else "disabled"
        self._convert_btn.configure(state=state)

    def _check_output_ready(self) -> bool:
        if self._output_mode_var.get() == OutputMode.FOLDER.value:
            return bool(self._folder_var.get().strip())
        return True

    # ------------------------------------------------------------------ output

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self._folder_var.set(folder)
            self._update_convert_button()

    # ------------------------------------------------------------------ conversion

    def _build_config(self) -> Optional[ConversionConfig]:
        fmt = OutputFormat.JPG if self._format_var.get() == "jpg" else OutputFormat.PNG
        mode_str = self._resize_var.get()
        resize_mode = next(m for m in ResizeMode if m.value == mode_str)
        w = _int_or_none(self._width_var.get())
        h = _int_or_none(self._height_var.get())

        out_mode_str = self._output_mode_var.get()
        out_mode = next(m for m in OutputMode if m.value == out_mode_str)

        folder = Path(self._folder_var.get().strip()) if self._folder_var.get().strip() else None
        suffix = self._suffix_var.get() or "_converted"

        return ConversionConfig(
            output_format=fmt,
            jpeg_quality=self._quality_var.get(),
            png_compression=self._compression_var.get(),
            resize=ResizeConfig(mode=resize_mode, width=w, height=h),
            output_mode=out_mode,
            output_folder=folder,
            alongside_suffix=suffix,
            preserve_exif=self._exif_var.get(),
        )

    def _validate_before_convert(self, config: ConversionConfig) -> bool:
        if config.output_mode == OutputMode.FOLDER and config.output_folder:
            try:
                config.output_folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Output Folder Error",
                                     f"Cannot create output folder:\n{exc}")
                return False
        return True

    def _start_conversion(self) -> None:
        config = self._build_config()
        if config is None:
            return
        if not self._validate_before_convert(config):
            return

        pending = [e["path"] for e in self._files if e["status"] == "pending"]
        if not pending:
            return

        self._converting = True
        self._convert_btn.configure(state="disabled")
        self._progress_bar.set(0)
        self._status_lbl.configure(text=f"Converting 0 of {len(pending)}…")
        self._log(f"--- Starting batch: {len(pending)} file(s) ---")

        # Reset pending rows to "converting"
        for entry, row in zip(self._files, self._rows):
            if entry["status"] == "pending":
                self._set_row_status(entry, row, "converting", "")

        thread = threading.Thread(
            target=self._do_conversion, args=(pending, config), daemon=True
        )
        thread.start()

    def _do_conversion(self, paths: List[Path], config: ConversionConfig) -> None:
        def on_progress(result: FileResult, done: int, total: int) -> None:
            self.after(0, lambda r=result, d=done, t=total: self._on_file_done(r, d, t))

        self._processor.convert_batch(paths, config, on_progress)
        self.after(0, self._on_batch_complete)

    def _on_file_done(self, result: FileResult, done: int, total: int) -> None:
        # Find matching entry & row
        for entry, row in zip(self._files, self._rows):
            if entry["path"] == result.path:
                if result.status == "success":
                    detail = f"{result.duration_ms}ms"
                    self._set_row_status(entry, row, "success", detail)
                    log_msg = f"✓ {result.path.name} → {result.output_path} ({result.duration_ms}ms)"
                    for note in result.notes:
                        self._log(f"  ℹ {note}")
                else:
                    self._set_row_status(entry, row, "error", result.error_message or "")
                    log_msg = f"✗ {result.path.name}: {result.error_message}"
                self._log(log_msg)
                break

        success_count = sum(1 for e in self._files if e["status"] == "success")
        error_count = sum(1 for e in self._files if e["status"] == "error")
        self._progress_bar.set(done / total)
        self._status_lbl.configure(
            text=f"{done} of {total} processed | {success_count} done | {error_count} failed"
        )

    def _on_batch_complete(self) -> None:
        self._converting = False
        success_count = sum(1 for e in self._files if e["status"] == "success")
        error_count = sum(1 for e in self._files if e["status"] == "error")
        self._log(f"--- Done: {success_count} succeeded, {error_count} failed ---")
        self._status_lbl.configure(
            text=f"Complete — {success_count} converted, {error_count} failed"
        )
        self._update_convert_button()

    def _set_row_status(self, entry: Dict, row: Dict, status: str, detail: str) -> None:
        entry["status"] = status
        entry["status_detail"] = detail
        text = _STATUS_TEXT[status]
        if status in ("error", "success") and detail:
            text = f"{_STATUS_TEXT[status]}  {detail}"
        row["status_lbl"].configure(text=text, text_color=_STATUS_COLOR[status])

    # ------------------------------------------------------------------ log

    def _log(self, message: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._log_box.get("1.0", "end"))

    def _export_log(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            Path(path).write_text(self._log_box.get("1.0", "end"), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Export Failed", str(exc))

    # ------------------------------------------------------------------ startup banner

    def _show_missing_deps_banner(self) -> None:
        missing = get_missing_info()
        if not missing:
            return
        lines = ["Optional format support unavailable:"]
        for fmt_name, cmd in missing:
            lines.append(f"  • {fmt_name}: {cmd}")
        self._log("\n".join(lines))
        self._log("These formats will be shown as unsupported in the file list.\n")
