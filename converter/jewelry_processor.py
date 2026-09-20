from __future__ import annotations

import logging
import threading
from typing import Optional, TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from .models import JewelryConfig

logger = logging.getLogger(__name__)

# Module-level session cache — one session reused across all images in a batch.
# onnxruntime InferenceSession is thread-safe for parallel inference calls.
_lock = threading.Lock()
_session: Optional[object] = None
_session_model: Optional[str] = None


def reset_session() -> None:
    """Force session reload on next use (e.g. after model change)."""
    global _session, _session_model
    with _lock:
        _session = None
        _session_model = None


def _get_session(config: "JewelryConfig") -> object:
    global _session, _session_model

    model = config.bg_model
    with _lock:
        if _session is not None and _session_model == model:
            return _session

        try:
            from rembg import new_session  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "rembg is not installed. Run:  pip install rembg[gpu]  (GPU) "
                "or  pip install rembg  (CPU only)."
            ) from exc

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if config.use_gpu
            else ["CPUExecutionProvider"]
        )
        logger.info("Loading rembg model '%s' (providers=%s)…", model, providers)
        _session = new_session(model, providers=providers)
        _session_model = model
        logger.info("rembg session ready.")
        return _session


# rembg's u2net model runs on 320×320 internally, so there's no quality gain
# from sending it a 12 MP photo — only a huge memory cost.  We cap the longer
# edge at this value before inference, then upscale the alpha mask back to the
# original size before compositing.
_REMBG_MAX_DIM = 1024


def _downscale_for_inference(img: Image.Image) -> tuple[Image.Image, tuple[int, int]]:
    original_size = img.size
    w, h = original_size
    if max(w, h) <= _REMBG_MAX_DIM:
        return img, original_size
    scale = _REMBG_MAX_DIM / max(w, h)
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS), original_size


def _remove_background(img: Image.Image, config: "JewelryConfig") -> Image.Image:
    try:
        from rembg import remove  # type: ignore
    except ImportError as exc:
        raise RuntimeError("rembg not installed.") from exc

    session = _get_session(config)

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Downscale to a safe size before inference to avoid OOM on large photos.
    img_small, original_size = _downscale_for_inference(img)

    result = remove(
        img_small,
        session=session,
        alpha_matting=config.alpha_matting,
        alpha_matting_foreground_threshold=config.alpha_matting_fg,
        alpha_matting_background_threshold=config.alpha_matting_bg,
        alpha_matting_erode_size=config.alpha_matting_erode,
    )

    if not isinstance(result, Image.Image):
        result = Image.fromarray(result)

    result = result.convert("RGBA")

    # Scale the masked result back up to original dimensions.
    if result.size != original_size:
        result = result.resize(original_size, Image.Resampling.LANCZOS)

    return result


def _content_bbox(img_rgba: Image.Image) -> tuple[int, int, int, int]:
    """Tight bounding box around non-transparent pixels (via alpha channel)."""
    bbox = img_rgba.split()[3].getbbox()
    return bbox if bbox else (0, 0, img_rgba.width, img_rgba.height)


def _place_on_canvas(img_rgba: Image.Image, config: "JewelryConfig") -> Image.Image:
    """Crop to content, fit inside canvas with margins, paste on white background."""
    bbox = _content_bbox(img_rgba)
    cropped = img_rgba.crop(bbox)

    cw, ch = config.canvas_width, config.canvas_height
    mx = int(cw * config.margin_pct)
    my = int(ch * config.margin_pct)

    max_w = max(1, cw - 2 * mx)
    max_h = max(1, ch - 2 * my)

    pw, ph = cropped.size
    if pw == 0 or ph == 0:
        canvas = Image.new("RGB", (cw, ch), config.background_color)
        return canvas

    scale = min(max_w / pw, max_h / ph)
    new_w = max(1, round(pw * scale))
    new_h = max(1, round(ph * scale))

    product = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (cw, ch), (*config.background_color, 255))
    paste_x = (cw - new_w) // 2
    paste_y = (ch - new_h) // 2
    canvas.paste(product, (paste_x, paste_y), mask=product.split()[3])

    return canvas.convert("RGB")


def apply_jewelry_pipeline(img: Image.Image, config: "JewelryConfig") -> Image.Image:
    """
    Full pipeline:
      1. Remove background → RGBA with product mask
      2. Crop to content bounding box
      3. Fit inside canvas with configurable margins
      4. Composite onto solid white (or custom color) background
      5. Return RGB image ready for encode
    """
    img_rgba = _remove_background(img, config)
    return _place_on_canvas(img_rgba, config)
