from __future__ import annotations

import os
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageOps

from .handlers import FormatHandlerRegistry
from .models import ConversionConfig, FileResult, OutputFormat, OutputMode, ResizeMode


def _make_error(path: Path, msg: str, start: float) -> FileResult:
    return FileResult(
        path=path,
        status="error",
        error_message=msg,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _get_output_path(source: Path, config: ConversionConfig) -> Path:
    ext = config.output_format.value
    if config.output_mode == OutputMode.FOLDER and config.output_folder:
        base = config.output_folder / f"{source.stem}.{ext}"
    else:
        stem = source.stem + config.alongside_suffix
        base = source.parent / f"{stem}.{ext}"

    if not base.exists():
        return base

    counter = 1
    while True:
        if config.output_mode == OutputMode.FOLDER and config.output_folder:
            candidate = config.output_folder / f"{source.stem}_{counter}.{ext}"
        else:
            stem = source.stem + config.alongside_suffix
            candidate = source.parent / f"{stem}_{counter}.{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def _apply_fit(img: Image.Image, w: Optional[int], h: Optional[int]) -> Image.Image:
    ow, oh = img.size
    if w and h:
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        return img
    if w:
        ratio = w / ow
        nh = max(1, int(oh * ratio))
        rs = Image.Resampling.LANCZOS if ratio < 1 else Image.Resampling.BICUBIC
        return img.resize((w, nh), rs)
    if h:
        ratio = h / oh
        nw = max(1, int(ow * ratio))
        rs = Image.Resampling.LANCZOS if ratio < 1 else Image.Resampling.BICUBIC
        return img.resize((nw, h), rs)
    return img


def _apply_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    ow, oh = img.size
    scale = max(w / ow, h / oh)
    nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
    rs = Image.Resampling.LANCZOS if scale < 1 else Image.Resampling.BICUBIC
    img = img.resize((nw, nh), rs)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _apply_resize(img: Image.Image, config: ConversionConfig) -> Image.Image:
    mode = config.resize.mode
    w, h = config.resize.width, config.resize.height
    if mode == ResizeMode.NONE:
        return img
    if mode == ResizeMode.FIT:
        return _apply_fit(img, w, h)
    if mode == ResizeMode.FILL and w and h:
        return _apply_fill(img, w, h)
    if mode == ResizeMode.STRETCH and w and h:
        return img.resize((w, h), Image.Resampling.LANCZOS)
    return img


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )


def _convert_mode(img: Image.Image, fmt: OutputFormat) -> Image.Image:
    if fmt == OutputFormat.JPG:
        return img.convert("RGB") if img.mode != "RGB" else img
    if _has_alpha(img):
        return img.convert("RGBA") if img.mode != "RGBA" else img
    return img.convert("RGB") if img.mode != "RGB" else img


def _ensure_output_dir(config: ConversionConfig) -> Optional[str]:
    if config.output_mode != OutputMode.FOLDER or not config.output_folder:
        return None
    try:
        config.output_folder.mkdir(parents=True, exist_ok=True)
        return None
    except OSError as exc:
        return str(exc)


def _save_image(
    img: Image.Image,
    path: Path,
    config: ConversionConfig,
    exif: Optional[bytes],
) -> None:
    if config.output_format == OutputFormat.JPG:
        kwargs: dict = {"format": "JPEG", "quality": config.jpeg_quality, "optimize": True}
        if config.preserve_exif and exif:
            kwargs["exif"] = exif
    else:
        kwargs = {"format": "PNG", "compress_level": config.png_compression}
        if config.preserve_exif and exif:
            kwargs["exif"] = exif
    img.save(path, **kwargs)


def _open_and_validate(
    path: Path, registry: FormatHandlerRegistry, start: float
) -> tuple[Image.Image, list[str]] | FileResult:
    if path.suffix.lower() not in registry.available_extensions:
        return _make_error(path, f"Unsupported format: {path.suffix}", start)

    handler = registry.get_handler(path.suffix.lower())
    if handler is None:
        return _make_error(path, f"No handler registered for {path.suffix}", start)

    try:
        img, notes = handler.open_with_notes(path)
    except Exception as exc:
        return _make_error(path, f"Could not open {path.name}: {exc}", start)

    return img, notes


def _transform_image(
    img: Image.Image, config: ConversionConfig, path: Path, start: float
) -> tuple[Image.Image, Optional[bytes]] | FileResult:
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    exif: Optional[bytes] = img.info.get("exif")

    try:
        img = _apply_resize(img, config)
    except Exception as exc:
        return _make_error(path, f"Resize failed for {path.name}: {exc}", start)

    img = _convert_mode(img, config.output_format)
    return img, exif


def process_file(
    path: Path, config: ConversionConfig, registry: FormatHandlerRegistry
) -> FileResult:
    start = time.monotonic()

    open_result = _open_and_validate(path, registry, start)
    if isinstance(open_result, FileResult):
        return open_result
    img, notes = open_result

    transform_result = _transform_image(img, config, path, start)
    if isinstance(transform_result, FileResult):
        return transform_result
    img, exif = transform_result

    dir_err = _ensure_output_dir(config)
    if dir_err:
        return _make_error(path, f"Cannot create output folder: {dir_err}", start)

    output_path = _get_output_path(path, config)

    try:
        _save_image(img, output_path, config, exif)
    except Exception as exc:
        return _make_error(path, f"Save failed for {path.name}: {exc}", start)

    return FileResult(
        path=path,
        status="success",
        notes=notes,
        duration_ms=int((time.monotonic() - start) * 1000),
        output_path=output_path,
    )


class BatchProcessor:
    def __init__(self, registry: FormatHandlerRegistry) -> None:
        self._registry = registry

    def convert_batch(
        self,
        paths: list[Path],
        config: ConversionConfig,
        progress_cb: Callable[[FileResult, int, int], None],
    ) -> None:
        max_workers = max(1, (os.cpu_count() or 2) - 1)
        total = len(paths)
        result_q: queue.Queue[FileResult] = queue.Queue()

        def task(p: Path) -> None:
            result_q.put(process_file(p, config, self._registry))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for p in paths:
                ex.submit(task, p)
            completed = 0
            while completed < total:
                try:
                    result = result_q.get(timeout=0.1)
                    completed += 1
                    progress_cb(result, completed, total)
                except queue.Empty:
                    continue
