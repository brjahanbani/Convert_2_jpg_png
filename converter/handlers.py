from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PIL import Image


class BaseHandler:
    def open(self, path: Path) -> Image.Image:
        raise NotImplementedError

    def get_notes(self, path: Path) -> list[str]:
        return []

    def open_with_notes(self, path: Path) -> tuple[Image.Image, list[str]]:
        return self.open(path), self.get_notes(path)


class JpegHandler(BaseHandler):
    def open(self, path: Path) -> Image.Image:
        img = Image.open(path)
        img.load()
        return img


class PngHandler(BaseHandler):
    def open(self, path: Path) -> Image.Image:
        img = Image.open(path)
        img.load()
        return img


class WebpHandler(BaseHandler):
    def open(self, path: Path) -> Image.Image:
        img = Image.open(path)
        img.load()
        return img


class BmpHandler(BaseHandler):
    def open(self, path: Path) -> Image.Image:
        img = Image.open(path)
        img.load()
        return img


class TiffHandler(BaseHandler):
    def open(self, path: Path) -> Image.Image:
        img = Image.open(path)
        img.load()
        return img


class GifHandler(BaseHandler):
    def open_with_notes(self, path: Path) -> tuple[Image.Image, list[str]]:
        img = Image.open(path)
        notes: list[str] = []
        try:
            if getattr(img, "n_frames", 1) > 1:
                notes.append(f"{path.name}: animated GIF — only first frame converted")
        except Exception:
            pass
        img.seek(0)
        frame = img.copy()
        return frame, notes

    def open(self, path: Path) -> Image.Image:
        return self.open_with_notes(path)[0]


class IcoHandler(BaseHandler):
    def open_with_notes(self, path: Path) -> tuple[Image.Image, list[str]]:
        img = Image.open(path)
        available = getattr(img, "sizes", None) or [img.size]
        n = len(available)
        w, h = img.size
        note = (
            f"{path.name}: extracted largest size ({w}×{h}) "
            f"from {n} available size{'s' if n != 1 else ''}"
        )
        img.load()
        return img, [note]

    def open(self, path: Path) -> Image.Image:
        return self.open_with_notes(path)[0]


class HeifHandler(BaseHandler):
    def open(self, path: Path) -> Image.Image:
        img = Image.open(path)
        img.load()
        return img


class AvifHandler(BaseHandler):
    def open(self, path: Path) -> Image.Image:
        img = Image.open(path)
        img.load()
        return img


class FormatHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, BaseHandler] = {}

    def register(self, extension: str, handler: BaseHandler) -> None:
        self._handlers[extension.lower()] = handler

    def get_handler(self, extension: str) -> Optional[BaseHandler]:
        return self._handlers.get(extension.lower())

    @property
    def available_extensions(self) -> set[str]:
        return set(self._handlers.keys())

    def is_supported(self, path: Path) -> bool:
        return path.suffix.lower() in self._handlers


def build_registry(deps: Dict[str, bool]) -> FormatHandlerRegistry:
    registry = FormatHandlerRegistry()

    for ext in (".jpg", ".jpeg", ".jfif", ".jpe"):
        registry.register(ext, JpegHandler())
    registry.register(".png", PngHandler())
    registry.register(".webp", WebpHandler())
    registry.register(".bmp", BmpHandler())
    registry.register(".gif", GifHandler())
    for ext in (".tiff", ".tif"):
        registry.register(ext, TiffHandler())
    registry.register(".ico", IcoHandler())

    if deps.get("heif"):
        for ext in (".heic", ".heif"):
            registry.register(ext, HeifHandler())

    if deps.get("avif"):
        registry.register(".avif", AvifHandler())

    return registry
