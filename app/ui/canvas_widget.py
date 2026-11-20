from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from app.core.blur import expand_and_clamp_box, render_blurred_image
from app.core.models import BlurConfig, Box, FaceRegion
from app.ui.workers import pil_rgb_to_qimage


class PhotoCanvasWidget(QWidget):
    """Interactive light-themed photo viewer with click-to-toggle faces and manual drag boxes."""

    face_toggled = Signal(str)
    face_hovered = Signal(object)  # str | None
    manual_box_added = Signal(object)  # Box
    manual_face_removed = Signal(str)
    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setMinimumSize(420, 360)

        self._source_image: Image.Image | None = None
        self._original_pixmap: QPixmap | None = None
        self._rendered_pixmap: QPixmap | None = None
        self._faces: list[FaceRegion] = []
        self._config = BlurConfig()
        self._show_original = False
        self._show_guides = True
        self._draw_mode = False
        self._selected_face_id: str | None = None

        self._drag_start_img: QPointF | None = None
        self._drag_curr_img: QPointF | None = None
        self._target_rect = QRectF()

    def set_photo(
        self,
        rgb_image: Image.Image | None,
        faces: list[FaceRegion],
        config: BlurConfig,
    ) -> None:
        self._source_image = rgb_image
        self._faces = faces
        self._config = config
        self._drag_start_img = None
        self._drag_curr_img = None

        if rgb_image is None:
            self._original_pixmap = None
            self._rendered_pixmap = None
            self.update()
            return

        self._original_pixmap = QPixmap.fromImage(pil_rgb_to_qimage(rgb_image))
        self.refresh_blur(faces, config)

    def refresh_blur(self, faces: list[FaceRegion], config: BlurConfig) -> None:
        self._faces = faces
        self._config = config
        if self._source_image is None:
            return
        rendered = render_blurred_image(self._source_image, faces, config)
        self._rendered_pixmap = QPixmap.fromImage(pil_rgb_to_qimage(rendered))
        self.update()

    def set_show_original(self, show: bool) -> None:
        if self._show_original != show:
            self._show_original = show
            self.update()

    def set_show_guides(self, show: bool) -> None:
        if self._show_guides != show:
            self._show_guides = show
            self.update()

    def set_draw_mode(self, enabled: bool) -> None:
        self._draw_mode = enabled
        self._drag_start_img = None
        self._drag_curr_img = None
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_selected_face(self, face_id: str | None) -> None:
        if self._selected_face_id != face_id:
            self._selected_face_id = face_id
            self.update()

    def _compute_target_rect(self) -> QRectF:
        if self._source_image is None:
            return QRectF()
        img_w, img_h = self._source_image.size
        pad = 16.0
        avail_w = max(1.0, self.width() - pad * 2)
        avail_h = max(1.0, self.height() - pad * 2)
        scale = min(avail_w / img_w, avail_h / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        left = (self.width() - draw_w) / 2.0
        top = (self.height() - draw_h) / 2.0
        return QRectF(left, top, draw_w, draw_h)

    def _widget_to_image(self, pos: QPointF) -> QPointF | None:
        if self._source_image is None or self._target_rect.isEmpty():
            return None
        img_w, img_h = self._source_image.size
        rx = (pos.x() - self._target_rect.left()) / self._target_rect.width()
        ry = (pos.y() - self._target_rect.top()) / self._target_rect.height()
        x = max(0.0, min(float(img_w), rx * img_w))
        y = max(0.0, min(float(img_h), ry * img_h))
        return QPointF(x, y)

    def _image_box_to_widget_rect(self, box: Box) -> QRectF:
        if self._source_image is None or self._target_rect.isEmpty():
            return QRectF()
        img_w, img_h = self._source_image.size
        sx = self._target_rect.width() / img_w
        sy = self._target_rect.height() / img_h
        return QRectF(
            self._target_rect.left() + box.x * sx,
            self._target_rect.top() + box.y * sy,
            box.width * sx,
            box.height * sy,
        )

    def _manual_delete_rect(self, face_rect: QRectF) -> QRectF:
        return QRectF(face_rect.right() - 10, face_rect.top() - 10, 20, 20)

    def _hit_test_face(self, pos: QPointF) -> tuple[FaceRegion | None, bool]:
        """Return (face, is_delete_button_hit)."""
        if self._source_image is None or self._show_original:
            return None, False

        img_w, img_h = self._source_image.size
        for face in reversed(self._faces):
            padded = expand_and_clamp_box(
                face.box,
                max(0.06, self._config.padding_ratio),
                img_w,
                img_h,
            )
            rect = self._image_box_to_widget_rect(padded)
            if face.source == "manual":
                del_rect = self._manual_delete_rect(rect)
                if del_rect.contains(pos):
                    return face, True

        best_face: FaceRegion | None = None
        best_dist_sq = float("inf")
        for face in reversed(self._faces):
            padded = expand_and_clamp_box(
                face.box,
                max(0.06, self._config.padding_ratio),
                img_w,
                img_h,
            )
            rect = self._image_box_to_widget_rect(padded)
            if rect.contains(pos):
                cx = rect.center().x()
                cy = rect.center().y()
                d2 = (pos.x() - cx) ** 2 + (pos.y() - cy) ** 2
                if d2 < best_dist_sq:
                    best_dist_sq = d2
                    best_face = face

        return best_face, False

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Clean light studio canvas background
        painter.fillRect(self.rect(), QColor("#F1F5F9"))

        pixmap = self._original_pixmap if self._show_original else self._rendered_pixmap
        if pixmap is None or self._source_image is None:
            return

        self._target_rect = self._compute_target_rect()

        # Subtle white frame around image
        frame_rect = self._target_rect.adjusted(-1, -1, 1, 1)
        painter.setPen(QPen(QColor("#CBD5E1"), 1))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawRect(frame_rect)

        painter.drawPixmap(self._target_rect.toRect(), pixmap)

        if self._show_original:
            self._draw_original_watermark(painter)
            return

        img_w, img_h = self._source_image.size
        badge_font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
        painter.setFont(badge_font)

        for index, face in enumerate(self._faces, start=1):
            is_selected = face.id == self._selected_face_id
            if not self._show_guides and not is_selected:
                continue

            padded = expand_and_clamp_box(
                face.box,
                self._config.padding_ratio,
                img_w,
                img_h,
            )
            rect = self._image_box_to_widget_rect(padded)

            if is_selected:
                border_color = QColor("#2563EB")
                fill_color = QColor(37, 99, 235, 24)
            elif face.blurred:
                border_color = QColor("#059669")
                fill_color = QColor(0, 0, 0, 0)
            else:
                border_color = QColor("#D97706")
                fill_color = QColor(245, 158, 11, 28)

            pen = QPen(border_color, 2.2 if is_selected else 1.8, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(fill_color))
            painter.drawRoundedRect(rect, 10, 10)

            # Badge pill (#N)
            label = f"#{index}"
            badge_bg = QColor("#2563EB") if is_selected else (
                QColor("#059669") if face.blurred else QColor("#D97706")
            )
            badge_w = 26 if index < 10 else 32
            badge_rect = QRectF(rect.left() + 4, max(self._target_rect.top() + 2, rect.top() - 10), badge_w, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(badge_bg))
            painter.drawRoundedRect(badge_rect, 9, 9)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, label)

            # Manual region delete button (×)
            if face.source == "manual" and not self._draw_mode:
                del_rect = self._manual_delete_rect(rect)
                painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
                painter.setBrush(QBrush(QColor("#E11D48")))
                painter.drawEllipse(del_rect)
                painter.drawText(del_rect, Qt.AlignmentFlag.AlignCenter, "×")

        # Draw active manual drag box
        if self._drag_start_img is not None and self._drag_curr_img is not None:
            x1 = min(self._drag_start_img.x(), self._drag_curr_img.x())
            y1 = min(self._drag_start_img.y(), self._drag_curr_img.y())
            w = abs(self._drag_curr_img.x() - self._drag_start_img.x())
            h = abs(self._drag_curr_img.y() - self._drag_start_img.y())
            draft_rect = self._image_box_to_widget_rect(Box(x1, y1, w, h))
            painter.setPen(QPen(QColor("#2563EB"), 2))
            painter.setBrush(QBrush(QColor(37, 99, 235, 42)))
            painter.drawRoundedRect(draft_rect, 8, 8)

    def _draw_original_watermark(self, painter: QPainter) -> None:
        badge = QRectF(self._target_rect.left() + 12, self._target_rect.top() + 12, 108, 26)
        painter.setPen(QPen(QColor("#2563EB"), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
        painter.drawRoundedRect(badge, 13, 13)
        painter.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#1D4ED8"))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "원본 미리보기")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._source_image is None:
            return
        pos = event.position()

        if self._draw_mode:
            if self._target_rect.contains(pos):
                img_pt = self._widget_to_image(pos)
                self._drag_start_img = img_pt
                self._drag_curr_img = img_pt
                self.update()
            return

        face, is_del = self._hit_test_face(pos)
        if face is not None:
            if is_del:
                self.manual_face_removed.emit(face.id)
            else:
                self.face_toggled.emit(face.id)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        if self._draw_mode:
            if self._drag_start_img is not None:
                self._drag_curr_img = self._widget_to_image(pos)
                self.update()
            return

        face, _ = self._hit_test_face(pos)
        new_id = face.id if face is not None else None
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if face is not None
            else Qt.CursorShape.ArrowCursor
        )
        if new_id != self._selected_face_id:
            self._selected_face_id = new_id
            self.face_hovered.emit(new_id)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._draw_mode
            and self._drag_start_img is not None
            and self._drag_curr_img is not None
        ):
            x1 = min(self._drag_start_img.x(), self._drag_curr_img.x())
            y1 = min(self._drag_start_img.y(), self._drag_curr_img.y())
            w = abs(self._drag_curr_img.x() - self._drag_start_img.x())
            h = abs(self._drag_curr_img.y() - self._drag_start_img.y())
            self._drag_start_img = None
            self._drag_curr_img = None
            self.update()
            if w >= 12.0 and h >= 12.0:
                self.manual_box_added.emit(Box(x=x1, y=y1, width=w, height=h))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
