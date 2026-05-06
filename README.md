# Bulk Image Converter

A standalone desktop GUI tool that converts batches of raster images to JPG or PNG, with optional resizing and quality control. Runs entirely offline and never overwrites source files.

---

## Requirements

- Python 3.10+
- See `requirements.txt`

---

## Install

```bash
# 1. Clone / download the project folder
cd 4-Convert_jpg_png

# 2. Create a virtual environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install core dependencies
pip install -r requirements.txt
```

---

## Optional Dependencies

### HEIC / HEIF support

| Platform | Command |
|----------|---------|
| Windows  | `pip install pillow-heif` |
| macOS    | `pip install pillow-heif` |
| Linux    | `sudo apt install libheif-dev` then `pip install pillow-heif` |

### AVIF support

**Pillow 10+ (recommended):** Install `libavif` at the system level, then Pillow picks it up automatically.

| Platform | Command |
|----------|---------|
| Windows  | Download `libavif` DLL or use `pip install pillow-avif-plugin` |
| macOS    | `brew install libavif` |
| Linux    | `sudo apt install libavif-dev` |

**Pillow < 10 / fallback:**
```bash
pip install pillow-avif-plugin
```

---

## Run

```bash
python main.py
```

---

## Supported Input Formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| JPEG   | `.jpg` `.jpeg` `.jfif` `.jpe` | All treated identically |
| PNG    | `.png` | |
| WebP   | `.webp` | |
| BMP    | `.bmp` | |
| GIF    | `.gif` | First frame only; animated GIFs logged as notice |
| TIFF   | `.tiff` `.tif` | |
| ICO    | `.ico` | Largest embedded size extracted automatically |
| HEIC/HEIF | `.heic` `.heif` | Requires `pillow-heif` |
| AVIF   | `.avif` | Requires `libavif` or `pillow-avif-plugin` |

---

## Features

- **Batch convert** — add files individually or scan a folder (optionally recursive)
- **Output formats** — JPG (quality 1–95) or PNG (compression 0–9)
- **Resize modes** — No Resize / Fit / Fill / Stretch with W×H inputs
- **Output strategies** — dedicated output folder or alongside source with custom suffix
- **EXIF auto-rotation** — phone photos oriented correctly automatically
- **Optional EXIF preservation** — strip by default, toggle to keep
- **No overwrites** — output filenames get `_1`, `_2`, … suffixes if needed
- **Concurrency** — uses all CPU cores minus one via `ThreadPoolExecutor`
- **Log panel** — per-file results; copy or export as `.txt`
- **Graceful degradation** — missing optional deps shown as informational banner; unsupported files flagged per-file, batch continues

---

## PyInstaller Packaging

```bash
pip install pyinstaller

# Single-file executable
pyinstaller --onefile --windowed \
    --add-data "converter;converter" \
    --add-data "ui;ui" \
    --hidden-import pillow_heif \
    --hidden-import PIL._tkinter_finder \
    main.py

# Output is in dist/main(.exe on Windows)
```

> **Note:** On Windows, CustomTkinter requires `--add-data` for its theme assets.
> If you see a blank window, add:
> ```
> --add-data ".venv/Lib/site-packages/customtkinter;customtkinter"
> ```

---

## Project Structure

```
4-Convert_jpg_png/
├── converter/
│   ├── models.py          # Data classes (ConversionConfig, FileResult, …)
│   ├── optional_deps.py   # Optional dependency bootstrap (one place, checked once)
│   ├── handlers.py        # FormatHandlerRegistry + per-format handler classes
│   └── processor.py       # Processing pipeline + BatchProcessor (no UI imports)
├── ui/
│   └── app.py             # CustomTkinter application (no Pillow imports)
├── main.py                # Entry point
├── requirements.txt
└── README.md
```

### Adding a new format

1. Create a handler class in `converter/handlers.py` that extends `BaseHandler`.
2. Register it in `build_registry()` — conditionally if it needs an optional dep.
3. Add its extensions to `_ALL_KNOWN_EXTS` and `_FORMAT_NAMES` in `ui/app.py`.

No other files need to change.
