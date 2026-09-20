from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


class OutputFormat(Enum):
    JPG = "jpg"
    PNG = "png"


class ResizeMode(Enum):
    NONE = "No Resize"
    FIT = "Fit"
    FILL = "Fill"
    STRETCH = "Stretch"


class OutputMode(Enum):
    FOLDER = "Output Folder"
    ALONGSIDE = "Alongside Source"


@dataclass
class ResizeConfig:
    mode: ResizeMode = ResizeMode.NONE
    width: Optional[int] = None
    height: Optional[int] = None


_BG_WHITE: Tuple[int, int, int] = (255, 255, 255)

JEWELRY_MODELS = [
    "u2net",
    "birefnet-general",
    "isnet-general-use",
    "birefnet-hires",
]


@dataclass
class JewelryConfig:
    """Settings for the jewelry background-removal pipeline."""
    enabled: bool = False
    bg_model: str = "u2net"
    use_gpu: bool = True
    canvas_width: int = 853
    canvas_height: int = 1280
    margin_pct: float = 0.08
    background_color: Tuple[int, int, int] = field(default_factory=lambda: _BG_WHITE)
    alpha_matting: bool = False
    alpha_matting_fg: int = 240
    alpha_matting_bg: int = 10
    alpha_matting_erode: int = 10


@dataclass
class ConversionConfig:
    output_format: OutputFormat = OutputFormat.JPG
    jpeg_quality: int = 85
    png_compression: int = 6
    resize: ResizeConfig = field(default_factory=ResizeConfig)
    output_mode: OutputMode = OutputMode.FOLDER
    output_folder: Optional[Path] = None
    alongside_suffix: str = "_converted"
    preserve_exif: bool = False
    jewelry: Optional[JewelryConfig] = None


@dataclass
class FileResult:
    path: Path
    status: str  # 'success' | 'error'
    error_message: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    duration_ms: int = 0
    output_path: Optional[Path] = None
