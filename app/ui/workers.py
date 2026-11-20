from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.core.blur import build_export_filename, export_clean_image_file
from app.core.detector import SCRFDDetector
from app.core.exif import inspect_image_metadata, load_upright_rgb_image
from app.core.models import BatchItem, BlurConfig, ExportFormat


def pil_rgb_to_qimage(img: Image.Image) -> QImage:
    rgb = img.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return qimg.copy()


class DetectionWorker(QThread):
    """Runs SCRFD face detection sequentially across queued photos without blocking UI."""

    item_started = Signal(str)
    item_finished = Signal(str, int, int, int, object, object, object)
    item_failed = Signal(str, str)
    progress = Signal(int, int)
    all_finished = Signal()

    def __init__(
        self,
        detector: SCRFDDetector,
        items: list[BatchItem],
        min_confidence: float,
        precision_mode: bool,
        keep_manual_faces: bool = True,
    ) -> None:
        super().__init__()
        self.detector = detector
        self.items = list(items)
        self.min_confidence = min_confidence
        self.precision_mode = precision_mode
        self.keep_manual_faces = keep_manual_faces

    def run(self) -> None:
        total = len(self.items)
        for idx, item in enumerate(self.items, start=1):
            if self.isInterruptionRequested():
                break

            self.item_started.emit(item.id)
            try:
                if item.memory_image_bytes is not None:
                    raw = item.memory_image_bytes
                    img = load_upright_rgb_image(raw)
                elif item.path is not None:
                    raw = item.path.read_bytes()
                    img = load_upright_rgb_image(raw)
                else:
                    raise ValueError("이미지 데이터가 없습니다.")

                exif = inspect_image_metadata(raw)
                width, height = img.size
                auto_faces = self.detector.detect(
                    img,
                    min_confidence=self.min_confidence,
                    precision_mode=self.precision_mode,
                )

                if self.keep_manual_faces:
                    manual_faces = [f for f in item.faces if f.source == "manual"]
                    faces = auto_faces + manual_faces
                else:
                    faces = auto_faces

                thumb_img = img.copy()
                thumb_img.thumbnail((96, 96), Image.Resampling.BILINEAR)
                thumb_qimg = pil_rgb_to_qimage(thumb_img)

                self.item_finished.emit(
                    item.id,
                    width,
                    height,
                    len(raw),
                    exif,
                    faces,
                    thumb_qimg,
                )
            except Exception as exc:  # noqa: BLE001
                self.item_failed.emit(item.id, str(exc))

            self.progress.emit(idx, total)

        self.all_finished.emit()


class BatchExportWorker(QThread):
    """Exports multiple photos into a target folder with EXIF verification."""

    progress = Signal(int, int, str)
    finished_all = Signal(int, int, int, str)
    failed = Signal(str)

    def __init__(
        self,
        items: list[BatchItem],
        config: BlurConfig,
        output_dir: Path,
        fmt: ExportFormat,
        quality: int = 92,
    ) -> None:
        super().__init__()
        self.items = list(items)
        self.config = config
        self.output_dir = output_dir
        self.fmt = fmt
        self.quality = quality

    def _unique_output_path(self, filename: str, used: set[str]) -> Path:
        candidate = filename
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 2
        while candidate.lower() in used:
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        used.add(candidate.lower())
        return self.output_dir / candidate

    def run(self) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            total = len(self.items)
            saved_count = 0
            total_bytes = 0
            clean_exif_count = 0
            used_names: set[str] = set()

            for idx, item in enumerate(self.items, start=1):
                if self.isInterruptionRequested():
                    break

                self.progress.emit(idx, total, item.display_name)
                source = item.memory_image_bytes if item.memory_image_bytes is not None else item.path
                if source is None:
                    continue

                rgb_img = load_upright_rgb_image(source)
                out_name = build_export_filename(item.display_name, self.fmt)
                out_path = self._unique_output_path(out_name, used_names)

                written_size, post_check = export_clean_image_file(
                    rgb_img,
                    item.faces,
                    self.config,
                    out_path,
                    self.fmt,
                    quality=self.quality,
                )
                saved_count += 1
                total_bytes += written_size
                if not post_check.has_metadata:
                    clean_exif_count += 1

            self.finished_all.emit(
                saved_count,
                total_bytes,
                clean_exif_count,
                str(self.output_dir),
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
