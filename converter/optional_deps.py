from __future__ import annotations

from typing import Dict

_deps: Dict[str, bool] = {}
_initialized = False


def initialize() -> Dict[str, bool]:
    global _deps, _initialized
    if _initialized:
        return _deps
    _check_heif()
    _check_avif()
    _check_rembg()
    _check_gpu()
    _initialized = True
    return _deps


def _check_heif() -> None:
    try:
        import pillow_heif  # type: ignore
        pillow_heif.register_heif_opener()
        _deps["heif"] = True
    except ImportError:
        _deps["heif"] = False


def _check_avif() -> None:
    try:
        import pillow_avif  # type: ignore  # noqa: F401
    except ImportError:
        pass
    try:
        from PIL import Image
        _deps["avif"] = ".avif" in Image.registered_extensions()
    except Exception:
        _deps["avif"] = False


def _check_rembg() -> None:
    try:
        import rembg  # type: ignore  # noqa: F401
        _deps["rembg"] = True
    except ImportError:
        _deps["rembg"] = False


def _check_gpu() -> None:
    try:
        import onnxruntime as ort  # type: ignore
        _deps["gpu"] = "CUDAExecutionProvider" in ort.get_available_providers()
    except ImportError:
        _deps["gpu"] = False


def get_missing_info() -> list[tuple[str, str]]:
    deps = initialize()
    missing: list[tuple[str, str]] = []
    if not deps.get("heif"):
        missing.append(("HEIC/HEIF", "pip install pillow-heif"))
    if not deps.get("avif"):
        missing.append(("AVIF", "pip install pillow-avif-plugin  # or install libavif"))
    return missing
