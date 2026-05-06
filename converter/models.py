from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


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


@dataclass
class FileResult:
    path: Path
    status: str  # 'success' | 'error'
    error_message: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    duration_ms: int = 0
    output_path: Optional[Path] = None
