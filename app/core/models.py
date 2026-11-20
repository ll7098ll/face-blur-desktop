from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


BlurStyle = Literal["gaussian", "mosaic"]
ExportFormat = Literal["JPEG", "PNG", "WEBP"]
ItemStatus = Literal["pending", "processing", "done", "error"]


@dataclass
class Box:
    x: float
    y: float
    width: float
    height: float


@dataclass
class FaceRegion:
    id: str
    box: Box
    score: float
    blurred: bool = True
    source: Literal["auto", "manual"] = "auto"


@dataclass
class BlurConfig:
    intensity: int = 65
    padding_ratio: float = 0.18
    min_confidence: float = 0.35
    style: BlurStyle = "gaussian"
    precision_mode: bool = True


@dataclass
class ExifInspection:
    has_metadata: bool
    tags: list[str] = field(default_factory=list)


@dataclass
class BatchItem:
    id: str
    path: Path | None
    display_name: str
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    exif: ExifInspection = field(default_factory=lambda: ExifInspection(False, []))
    faces: list[FaceRegion] = field(default_factory=list)
    status: ItemStatus = "pending"
    error_message: str | None = None
    # For clipboard-pasted images that have no file path on disk
    memory_image_bytes: bytes | None = None

    @property
    def blurred_count(self) -> int:
        return sum(1 for f in self.faces if f.blurred)
