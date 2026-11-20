from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.blur import build_export_filename, export_clean_image_file
from app.core.detector import SCRFDDetector
from app.core.exif import load_upright_rgb_image
from app.core.models import BatchItem, BlurConfig, Box, ExportFormat, FaceRegion
from app.ui.canvas_widget import PhotoCanvasWidget
from app.ui.workers import BatchExportWorker, DetectionWorker

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def format_bytes(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


class MainWindow(QMainWindow):
    def __init__(self, detector: SCRFDDetector | None = None) -> None:
        super().__init__()
        self.setWindowTitle("얼굴블러 · 고정밀 오프라인 얼굴 보호")
        self.resize(1320, 820)
        self.setMinimumSize(1020, 680)
        self.setAcceptDrops(True)

        self.detector = detector or SCRFDDetector()
        self.config = BlurConfig()
        self.export_format: ExportFormat = "JPEG"

        self.items: list[BatchItem] = []
        self.item_map: dict[str, BatchItem] = {}
        self.thumb_icons: dict[str, QIcon] = {}
        self.current_item_id: str | None = None
        self.current_image: Image.Image | None = None

        self._detect_worker: DetectionWorker | None = None
        self._pending_detect_ids: list[str] = []
        self._export_worker: BatchExportWorker | None = None

        self._build_ui()
        self._setup_shortcuts()
        self._update_ui_state()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # ── Top Header Bar ──────────────────────────────────────────────
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 12, 20, 12)
        top_layout.setSpacing(12)

        brand_box = QVBoxLayout()
        brand_box.setSpacing(2)
        title_lbl = QLabel("얼굴블러")
        title_lbl.setObjectName("BrandTitle")
        sub_lbl = QLabel("고정밀 SCRFD AI · 여러 장 동시 처리 · EXIF 메타데이터 자동 삭제")
        sub_lbl.setObjectName("BrandSub")
        brand_box.addWidget(title_lbl)
        brand_box.addWidget(sub_lbl)
        top_layout.addLayout(brand_box)

        top_layout.addStretch(1)

        privacy_pill = QLabel("● 100% 오프라인 로컬 처리 · 서버 전송 없음")
        privacy_pill.setObjectName("PrivacyPill")
        top_layout.addWidget(privacy_pill)

        self.add_files_btn = QPushButton("사진 추가")
        self.add_files_btn.clicked.connect(self._open_files_dialog)
        top_layout.addWidget(self.add_files_btn)

        self.add_folder_btn = QPushButton("폴더 추가")
        self.add_folder_btn.clicked.connect(self._open_folder_dialog)
        top_layout.addWidget(self.add_folder_btn)

        root_layout.addWidget(top_bar)

        # ── Main 3-Column Body ──────────────────────────────────────────
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(14)
        root_layout.addWidget(body, 1)

        # Left Column: Batch Photo Queue
        body_layout.addWidget(self._build_queue_panel())

        # Center Column: Empty Dropzone / Interactive Canvas
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self._build_empty_dropzone())
        self.center_stack.addWidget(self._build_canvas_panel())
        body_layout.addWidget(self.center_stack, 1)

        # Right Column: Face List + Settings + Export (Scrollable)
        body_layout.addWidget(self._build_right_sidebar())

    def _build_queue_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setFixedWidth(250)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.queue_title = QLabel("사진 목록 (0장)")
        self.queue_title.setObjectName("SectionTitle")
        header.addWidget(self.queue_title)
        header.addStretch(1)

        self.clear_queue_btn = QPushButton("비우기")
        self.clear_queue_btn.setObjectName("SmallChip")
        self.clear_queue_btn.clicked.connect(self._clear_all_items)
        header.addWidget(self.clear_queue_btn)
        layout.addLayout(header)

        self.queue_list = QListWidget()
        self.queue_list.setIconSize(QSize(48, 48))
        self.queue_list.setSpacing(2)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.queue_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.queue_list.currentRowChanged.connect(self._on_queue_row_changed)
        layout.addWidget(self.queue_list, 1)

        self.queue_progress_label = QLabel("대기 중인 작업 없음")
        self.queue_progress_label.setObjectName("MutedText")
        layout.addWidget(self.queue_progress_label)

        self.queue_progress = QProgressBar()
        self.queue_progress.setRange(0, 100)
        self.queue_progress.setValue(0)
        self.queue_progress.setTextVisible(False)
        self.queue_progress.hide()
        layout.addWidget(self.queue_progress)

        bottom_btns = QHBoxLayout()
        bottom_btns.setSpacing(6)
        self.remove_item_btn = QPushButton("선택 삭제")
        self.remove_item_btn.setObjectName("SmallChip")
        self.remove_item_btn.clicked.connect(self._remove_current_item)
        bottom_btns.addWidget(self.remove_item_btn)

        self.redetect_all_btn = QPushButton("전체 재감지")
        self.redetect_all_btn.setObjectName("SmallChip")
        self.redetect_all_btn.clicked.connect(self._redetect_all_items)
        bottom_btns.addWidget(self.redetect_all_btn)
        layout.addLayout(bottom_btns)

        return card

    def _build_empty_dropzone(self) -> QWidget:
        wrapper = QWidget()
        wrap_layout = QVBoxLayout(wrapper)
        wrap_layout.setContentsMargins(0, 0, 0, 0)

        self.dropzone = QFrame()
        self.dropzone.setObjectName("DropZone")
        dz_layout = QVBoxLayout(self.dropzone)
        dz_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_layout.setSpacing(12)
        dz_layout.setContentsMargins(36, 48, 36, 48)

        title = QLabel("사진 파일 여러 장이나 폴더를 여기에 끌어다 놓으세요")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_layout.addWidget(title)

        desc = QLabel(
            "JPG · PNG · WebP 지원 · 클립보드 붙여넣기(Ctrl+V) 가능\n"
            "배경 속 작은 얼굴과 옆모습까지 오프라인 AI(SCRFD)로 자동 감지합니다."
        )
        desc.setObjectName("MutedText")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pick_files = QPushButton("사진 여러 장 선택하기")
        pick_files.setObjectName("PrimaryBtn")
        pick_files.clicked.connect(self._open_files_dialog)
        btn_row.addWidget(pick_files)

        pick_folder = QPushButton("폴더 통째로 불러오기")
        pick_folder.clicked.connect(self._open_folder_dialog)
        btn_row.addWidget(pick_folder)

        dz_layout.addSpacing(6)
        dz_layout.addLayout(btn_row)

        wrap_layout.addWidget(self.dropzone, 1)
        return wrapper

    def _build_canvas_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("CanvasCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self.canvas_hint = QLabel("사진 속 얼굴을 클릭하면 블러를 해제하거나 다시 켤 수 있습니다")
        self.canvas_hint.setObjectName("MutedText")
        toolbar.addWidget(self.canvas_hint)
        toolbar.addStretch(1)

        self.compare_btn = QPushButton("꾹 눌러서 원본 비교 (Space)")
        self.compare_btn.setObjectName("SmallChip")
        self.compare_btn.pressed.connect(lambda: self._set_show_original(True))
        self.compare_btn.released.connect(lambda: self._set_show_original(False))
        toolbar.addWidget(self.compare_btn)
        layout.addLayout(toolbar)

        self.canvas = PhotoCanvasWidget()
        self.canvas.face_toggled.connect(self._toggle_face)
        self.canvas.face_hovered.connect(self._on_canvas_face_hovered)
        self.canvas.manual_box_added.connect(self._add_manual_box)
        self.canvas.manual_face_removed.connect(self._remove_face)
        self.canvas.files_dropped.connect(self.add_paths)
        layout.addWidget(self.canvas, 1)

        return card

    def _build_right_sidebar(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(322)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        # ── Card 1: Detected Faces ─────────────────────────────────────
        face_card = QFrame()
        face_card.setObjectName("Card")
        fc_layout = QVBoxLayout(face_card)
        fc_layout.setContentsMargins(12, 12, 12, 12)
        fc_layout.setSpacing(8)

        fc_head = QHBoxLayout()
        self.faces_title = QLabel("감지된 얼굴 (0)")
        self.faces_title.setObjectName("SectionTitle")
        fc_head.addWidget(self.faces_title)
        fc_head.addStretch(1)
        self.blur_count_badge = QLabel("블러 0/0")
        self.blur_count_badge.setObjectName("CountBadge")
        fc_head.addWidget(self.blur_count_badge)
        fc_layout.addLayout(fc_head)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        self.blur_all_btn = QPushButton("전체 블러")
        self.blur_all_btn.setObjectName("SmallChip")
        self.blur_all_btn.clicked.connect(lambda: self._set_all_faces_blurred(True))
        quick_row.addWidget(self.blur_all_btn)

        self.unblur_all_btn = QPushButton("전체 해제")
        self.unblur_all_btn.setObjectName("SmallChip")
        self.unblur_all_btn.clicked.connect(lambda: self._set_all_faces_blurred(False))
        quick_row.addWidget(self.unblur_all_btn)

        self.draw_mode_btn = QPushButton("+ 직접 추가")
        self.draw_mode_btn.setObjectName("SmallChip")
        self.draw_mode_btn.setCheckable(True)
        self.draw_mode_btn.toggled.connect(self._on_draw_mode_toggled)
        quick_row.addWidget(self.draw_mode_btn)
        fc_layout.addLayout(quick_row)

        self.face_list = QListWidget()
        self.face_list.setMaximumHeight(118)
        self.face_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.face_list.itemClicked.connect(self._on_face_list_clicked)
        fc_layout.addWidget(self.face_list)

        self.show_guides_cb = QCheckBox("얼굴 테두리 가이드 표시")
        self.show_guides_cb.setChecked(True)
        self.show_guides_cb.toggled.connect(self.canvas.set_show_guides)
        fc_layout.addWidget(self.show_guides_cb)

        layout.addWidget(face_card)

        # ── Card 2: Blur & Detection Settings ──────────────────────────
        cfg_card = QFrame()
        cfg_card.setObjectName("Card")
        cfg_layout = QVBoxLayout(cfg_card)
        cfg_layout.setContentsMargins(14, 14, 14, 14)
        cfg_layout.setSpacing(10)

        cfg_title = QLabel("블러 · 감지 설정")
        cfg_title.setObjectName("SectionTitle")
        cfg_layout.addWidget(cfg_title)

        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        self.gaussian_btn = QPushButton("부드러운 블러")
        self.gaussian_btn.setProperty("active", True)
        self.gaussian_btn.clicked.connect(lambda: self._set_blur_style("gaussian"))
        style_row.addWidget(self.gaussian_btn)

        self.mosaic_btn = QPushButton("모자이크")
        self.mosaic_btn.setProperty("active", False)
        self.mosaic_btn.clicked.connect(lambda: self._set_blur_style("mosaic"))
        style_row.addWidget(self.mosaic_btn)
        cfg_layout.addLayout(style_row)

        self.precision_cb = QCheckBox("정밀 감지 모드 (배경 작은 얼굴·옆모습 강화)")
        self.precision_cb.setChecked(self.config.precision_mode)
        self.precision_cb.toggled.connect(self._on_precision_toggled)
        cfg_layout.addWidget(self.precision_cb)

        # Intensity slider
        int_head = QHBoxLayout()
        int_head.addWidget(QLabel("블러 강도"))
        int_head.addStretch(1)
        self.intensity_val_lbl = QLabel(f"{self.config.intensity}%")
        self.intensity_val_lbl.setObjectName("MutedText")
        int_head.addWidget(self.intensity_val_lbl)
        cfg_layout.addLayout(int_head)

        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider.setRange(10, 100)
        self.intensity_slider.setValue(self.config.intensity)
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)
        cfg_layout.addWidget(self.intensity_slider)

        # Padding slider
        pad_head = QHBoxLayout()
        pad_head.addWidget(QLabel("블러 범위 여백"))
        pad_head.addStretch(1)
        self.padding_val_lbl = QLabel(f"{round(self.config.padding_ratio * 100)}%")
        self.padding_val_lbl.setObjectName("MutedText")
        pad_head.addWidget(self.padding_val_lbl)
        cfg_layout.addLayout(pad_head)

        self.padding_slider = QSlider(Qt.Orientation.Horizontal)
        self.padding_slider.setRange(0, 40)
        self.padding_slider.setValue(round(self.config.padding_ratio * 100))
        self.padding_slider.valueChanged.connect(self._on_padding_changed)
        cfg_layout.addWidget(self.padding_slider)

        # Sensitivity slider
        conf_head = QHBoxLayout()
        conf_head.addWidget(QLabel("감지 민감도 (낮을수록 더 많이 찾음)"))
        conf_head.addStretch(1)
        self.conf_val_lbl = QLabel(f"{round(self.config.min_confidence * 100)}%")
        self.conf_val_lbl.setObjectName("MutedText")
        conf_head.addWidget(self.conf_val_lbl)
        cfg_layout.addLayout(conf_head)

        conf_row = QHBoxLayout()
        conf_row.setSpacing(6)
        self.conf_slider = QSlider(Qt.Orientation.Horizontal)
        self.conf_slider.setRange(20, 80)
        self.conf_slider.setSingleStep(5)
        self.conf_slider.setValue(round(self.config.min_confidence * 100))
        self.conf_slider.valueChanged.connect(self._on_confidence_changed)
        conf_row.addWidget(self.conf_slider, 1)

        self.redetect_one_btn = QPushButton("재감지")
        self.redetect_one_btn.setObjectName("SmallChip")
        self.redetect_one_btn.clicked.connect(self._redetect_current_item)
        conf_row.addWidget(self.redetect_one_btn)
        cfg_layout.addLayout(conf_row)

        layout.addWidget(cfg_card)

        # ── Card 3: Privacy & Export ───────────────────────────────────
        exp_card = QFrame()
        exp_card.setObjectName("Card")
        exp_layout = QVBoxLayout(exp_card)
        exp_layout.setContentsMargins(14, 14, 14, 14)
        exp_layout.setSpacing(10)

        exp_head = QHBoxLayout()
        exp_title = QLabel("개인정보 보호 · 저장")
        exp_title.setObjectName("SectionTitle")
        exp_head.addWidget(exp_title)
        exp_head.addStretch(1)
        self.dim_badge = QLabel("-")
        self.dim_badge.setObjectName("CountBadge")
        exp_head.addWidget(self.dim_badge)
        exp_layout.addLayout(exp_head)

        self.exif_status_lbl = QLabel("사진을 불러오면 EXIF 메타데이터를 자동 검사합니다.")
        self.exif_status_lbl.setObjectName("ExifClean")
        self.exif_status_lbl.setWordWrap(True)
        exp_layout.addWidget(self.exif_status_lbl)

        self.format_combo = QComboBox()
        self.format_combo.addItem("JPEG (용량 최적화)", "JPEG")
        self.format_combo.addItem("PNG (무손실)", "PNG")
        self.format_combo.addItem("WebP (고화질·소용량)", "WEBP")
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        exp_layout.addWidget(self.format_combo)

        self.save_one_btn = QPushButton("현재 사진 안전하게 저장")
        self.save_one_btn.setObjectName("PrimaryBtn")
        self.save_one_btn.clicked.connect(self._export_current_photo)
        exp_layout.addWidget(self.save_one_btn)

        self.save_all_btn = QPushButton("전체 0장 폴더에 일괄 저장")
        self.save_all_btn.setObjectName("BatchBtn")
        self.save_all_btn.clicked.connect(self._export_all_photos)
        exp_layout.addWidget(self.save_all_btn)

        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_progress.setTextVisible(False)
        self.export_progress.hide()
        exp_layout.addWidget(self.export_progress)

        self.export_result_lbl = QLabel("")
        self.export_result_lbl.setObjectName("ExportSuccess")
        self.export_result_lbl.setWordWrap(True)
        self.export_result_lbl.hide()
        exp_layout.addWidget(self.export_result_lbl)

        layout.addWidget(exp_card)
        layout.addStretch(1)

        scroll.setWidget(container)
        return scroll

    def _setup_shortcuts(self) -> None:
        paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        paste_shortcut.activated.connect(self._paste_from_clipboard)

    # ── File / Folder / Clipboard Ingestion ────────────────────────────
    def _open_files_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "블러 처리할 사진 선택 (여러 장 가능)",
            "",
            "이미지 파일 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)",
        )
        if files:
            self.add_paths([Path(f) for f in files])

    def _open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "사진이 들어 있는 폴더 선택")
        if folder:
            self.add_paths([Path(folder)])

    def _paste_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasUrls():
            paths = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
            if paths:
                self.add_paths(paths)
                return

        if mime.hasImage():
            qimg = clipboard.image()
            if not qimg.isNull():
                qbuf = QBuffer()
                qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
                qimg.save(qbuf, "PNG")
                raw = bytes(qbuf.data())
                qbuf.close()
                item = BatchItem(
                    id=uuid.uuid4().hex[:10],
                    path=None,
                    display_name=f"clipboard_{len(self.items) + 1}.png",
                    memory_image_bytes=raw,
                )
                self._enqueue_items([item])

    def add_paths(self, paths: list[Path]) -> None:
        collected: list[Path] = []
        for p in paths:
            if p.is_dir():
                for child in sorted(p.iterdir()):
                    if child.is_file() and child.suffix.lower() in SUPPORTED_EXTS:
                        collected.append(child)
            elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                collected.append(p)

        if not collected:
            QMessageBox.information(
                self,
                "지원 이미지 없음",
                "불러올 수 있는 이미지 파일(JPG, PNG, WebP 등)이 없습니다.",
            )
            return

        new_items: list[BatchItem] = []
        existing_paths = {it.path.resolve() for it in self.items if it.path is not None}
        for path in collected:
            resolved = path.resolve()
            if resolved in existing_paths:
                continue
            existing_paths.add(resolved)
            new_items.append(
                BatchItem(
                    id=uuid.uuid4().hex[:10],
                    path=resolved,
                    display_name=path.name,
                )
            )

        if new_items:
            self._enqueue_items(new_items)

    def _enqueue_items(self, new_items: list[BatchItem]) -> None:
        first_new_index = len(self.items)
        for item in new_items:
            self.items.append(item)
            self.item_map[item.id] = item
            list_item = QListWidgetItem(f"{item.display_name}\n대기 중...")
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.queue_list.addItem(list_item)
            self._pending_detect_ids.append(item.id)

        if self.current_item_id is None and self.items:
            self.queue_list.setCurrentRow(first_new_index)

        self.export_result_lbl.hide()
        self._update_ui_state()
        self._start_next_detection_batch()

    # ── Background Detection Queue ─────────────────────────────────────
    def _start_next_detection_batch(self) -> None:
        if self._detect_worker is not None and self._detect_worker.isRunning():
            return
        if not self._pending_detect_ids:
            self.queue_progress.hide()
            self.queue_progress_label.setText(f"총 {len(self.items)}장 준비 완료")
            self._update_ui_state()
            return

        batch_ids = list(self._pending_detect_ids)
        self._pending_detect_ids.clear()
        batch_items = [self.item_map[i] for i in batch_ids if i in self.item_map]
        if not batch_items:
            return

        self.queue_progress.setRange(0, len(batch_items))
        self.queue_progress.setValue(0)
        self.queue_progress.show()
        self.queue_progress_label.setText(f"AI 얼굴 감지 중... (0/{len(batch_items)})")

        worker = DetectionWorker(
            detector=self.detector,
            items=batch_items,
            min_confidence=self.config.min_confidence,
            precision_mode=self.config.precision_mode,
            keep_manual_faces=True,
        )
        worker.item_started.connect(self._on_detect_item_started)
        worker.item_finished.connect(self._on_detect_item_finished)
        worker.item_failed.connect(self._on_detect_item_failed)
        worker.progress.connect(self._on_detect_progress)
        worker.all_finished.connect(self._on_detect_batch_finished)
        self._detect_worker = worker
        worker.start()
        self._update_ui_state()

    def _find_queue_row(self, item_id: str) -> int:
        for row in range(self.queue_list.count()):
            w_item = self.queue_list.item(row)
            if w_item and w_item.data(Qt.ItemDataRole.UserRole) == item_id:
                return row
        return -1

    def _refresh_queue_item_text(self, item: BatchItem) -> None:
        row = self._find_queue_row(item.id)
        if row < 0:
            return
        w_item = self.queue_list.item(row)
        if w_item is None:
            return

        if item.status == "processing":
            sub = "얼굴 분석 중..."
        elif item.status == "error":
            sub = "오류 발생"
        elif item.status == "done":
            sub = f"얼굴 {len(item.faces)}명 · 블러 {item.blurred_count}"
        else:
            sub = "대기 중..."

        w_item.setText(f"{item.display_name}\n{sub}")
        icon = self.thumb_icons.get(item.id)
        if icon is not None:
            w_item.setIcon(icon)

    def _on_detect_item_started(self, item_id: str) -> None:
        item = self.item_map.get(item_id)
        if item is None:
            return
        item.status = "processing"
        self._refresh_queue_item_text(item)

    def _on_detect_item_finished(
        self,
        item_id: str,
        width: int,
        height: int,
        file_size: int,
        exif: object,
        faces: object,
        thumb_qimg: object,
    ) -> None:
        item = self.item_map.get(item_id)
        if item is None:
            return
        item.width = width
        item.height = height
        item.file_size_bytes = file_size
        item.exif = exif  # type: ignore[assignment]
        item.faces = faces  # type: ignore[assignment]
        item.status = "done"
        item.error_message = None

        self.thumb_icons[item_id] = QIcon(QPixmap.fromImage(thumb_qimg))  # type: ignore[arg-type]
        self._refresh_queue_item_text(item)

        if item_id == self.current_item_id:
            self._load_item_into_editor(item)

    def _on_detect_item_failed(self, item_id: str, error_msg: str) -> None:
        item = self.item_map.get(item_id)
        if item is None:
            return
        item.status = "error"
        item.error_message = error_msg
        self._refresh_queue_item_text(item)

    def _on_detect_progress(self, done: int, total: int) -> None:
        self.queue_progress.setValue(done)
        self.queue_progress_label.setText(f"AI 얼굴 감지 중... ({done}/{total})")

    def _on_detect_batch_finished(self) -> None:
        self._detect_worker = None
        if self._pending_detect_ids:
            self._start_next_detection_batch()
        else:
            self.queue_progress.hide()
            self.queue_progress_label.setText(
                f"총 {len(self.items)}장 감지 완료" if self.items else "대기 중인 작업 없음"
            )
            self._update_ui_state()

    # ── Editor Selection & Face Toggling ───────────────────────────────
    def _on_queue_row_changed(self, row: int) -> None:
        if row < 0 or row >= self.queue_list.count():
            self.current_item_id = None
            self.current_image = None
            self.canvas.set_photo(None, [], self.config)
            self._update_ui_state()
            return

        w_item = self.queue_list.item(row)
        item_id = w_item.data(Qt.ItemDataRole.UserRole)
        item = self.item_map.get(item_id)
        if item is None:
            return
        self.current_item_id = item.id
        self._load_item_into_editor(item)

    def _load_item_into_editor(self, item: BatchItem) -> None:
        try:
            source = item.memory_image_bytes if item.memory_image_bytes is not None else item.path
            if source is not None:
                self.current_image = load_upright_rgb_image(source)
                if item.width == 0:
                    item.width, item.height = self.current_image.size
                self.canvas.set_photo(self.current_image, item.faces, self.config)
            else:
                self.current_image = None
                self.canvas.set_photo(None, [], self.config)
        except Exception as exc:  # noqa: BLE001
            self.current_image = None
            self.canvas.set_photo(None, [], self.config)
            QMessageBox.warning(self, "사진 열기 실패", f"{item.display_name}: {exc}")

        self._refresh_face_list(item)
        self._update_ui_state()

    def _get_current_item(self) -> BatchItem | None:
        if self.current_item_id is None:
            return None
        return self.item_map.get(self.current_item_id)

    def _refresh_face_list(self, item: BatchItem | None) -> None:
        self.face_list.clear()
        if item is None:
            self.faces_title.setText("감지된 얼굴 (0)")
            self.blur_count_badge.setText("블러 0/0")
            return

        self.faces_title.setText(f"감지된 얼굴 ({len(item.faces)})")
        self.blur_count_badge.setText(f"블러 {item.blurred_count}/{len(item.faces)}")

        for idx, face in enumerate(item.faces, start=1):
            prefix = "수동 영역" if face.source == "manual" else "얼굴"
            state = "블러 ON" if face.blurred else "원본 유지(해제됨)"
            dot = "●" if face.blurred else "○"
            li = QListWidgetItem(f"{dot}  {prefix} #{idx}   —   {state}")
            li.setData(Qt.ItemDataRole.UserRole, face.id)
            self.face_list.addItem(li)

    def _toggle_face(self, face_id: str) -> None:
        item = self._get_current_item()
        if item is None:
            return
        for face in item.faces:
            if face.id == face_id:
                face.blurred = not face.blurred
                break
        self.canvas.refresh_blur(item.faces, self.config)
        self._refresh_face_list(item)
        self._refresh_queue_item_text(item)
        self.export_result_lbl.hide()

    def _on_face_list_clicked(self, list_item: QListWidgetItem) -> None:
        face_id = list_item.data(Qt.ItemDataRole.UserRole)
        if face_id:
            self._toggle_face(face_id)

    def _on_canvas_face_hovered(self, face_id: object) -> None:
        self.canvas.set_selected_face(face_id if isinstance(face_id, str) else None)

    def _set_all_faces_blurred(self, blurred: bool) -> None:
        item = self._get_current_item()
        if item is None:
            return
        for face in item.faces:
            face.blurred = blurred
        self.canvas.refresh_blur(item.faces, self.config)
        self._refresh_face_list(item)
        self._refresh_queue_item_text(item)
        self.export_result_lbl.hide()

    def _on_draw_mode_toggled(self, checked: bool) -> None:
        self.draw_mode_btn.setProperty("active", checked)
        self.draw_mode_btn.style().unpolish(self.draw_mode_btn)
        self.draw_mode_btn.style().polish(self.draw_mode_btn)
        self.canvas.set_draw_mode(checked)
        self.canvas_hint.setText(
            "사진 위를 드래그해 블러 영역을 직접 추가하세요"
            if checked
            else "사진 속 얼굴을 클릭하면 블러를 해제하거나 다시 켤 수 있습니다"
        )

    def _add_manual_box(self, box: Box) -> None:
        item = self._get_current_item()
        if item is None:
            return
        new_face = FaceRegion(
            id=f"manual-{uuid.uuid4().hex[:8]}",
            box=box,
            score=1.0,
            blurred=True,
            source="manual",
        )
        item.faces.append(new_face)
        self.draw_mode_btn.setChecked(False)
        self.canvas.refresh_blur(item.faces, self.config)
        self._refresh_face_list(item)
        self._refresh_queue_item_text(item)
        self.export_result_lbl.hide()

    def _remove_face(self, face_id: str) -> None:
        item = self._get_current_item()
        if item is None:
            return
        item.faces = [f for f in item.faces if f.id != face_id]
        self.canvas.refresh_blur(item.faces, self.config)
        self._refresh_face_list(item)
        self._refresh_queue_item_text(item)
        self.export_result_lbl.hide()

    # ── Settings Handlers ──────────────────────────────────────────────
    def _set_blur_style(self, style: str) -> None:
        self.config.style = "mosaic" if style == "mosaic" else "gaussian"
        self.gaussian_btn.setProperty("active", self.config.style == "gaussian")
        self.mosaic_btn.setProperty("active", self.config.style == "mosaic")
        for btn in (self.gaussian_btn, self.mosaic_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        item = self._get_current_item()
        if item is not None:
            self.canvas.refresh_blur(item.faces, self.config)

    def _on_precision_toggled(self, checked: bool) -> None:
        self.config.precision_mode = checked

    def _on_intensity_changed(self, value: int) -> None:
        self.config.intensity = value
        self.intensity_val_lbl.setText(f"{value}%")
        item = self._get_current_item()
        if item is not None:
            self.canvas.refresh_blur(item.faces, self.config)

    def _on_padding_changed(self, value: int) -> None:
        self.config.padding_ratio = value / 100.0
        self.padding_val_lbl.setText(f"{value}%")
        item = self._get_current_item()
        if item is not None:
            self.canvas.refresh_blur(item.faces, self.config)

    def _on_confidence_changed(self, value: int) -> None:
        snapped = round(value / 5) * 5
        self.config.min_confidence = snapped / 100.0
        self.conf_val_lbl.setText(f"{snapped}%")

    def _on_format_changed(self) -> None:
        data = self.format_combo.currentData()
        if data in ("JPEG", "PNG", "WEBP"):
            self.export_format = data

    def _redetect_current_item(self) -> None:
        item = self._get_current_item()
        if item is None:
            return
        if item.id not in self._pending_detect_ids:
            self._pending_detect_ids.append(item.id)
        self._start_next_detection_batch()

    def _redetect_all_items(self) -> None:
        if not self.items:
            return
        for item in self.items:
            if item.id not in self._pending_detect_ids:
                self._pending_detect_ids.append(item.id)
        self._start_next_detection_batch()

    def _remove_current_item(self) -> None:
        row = self.queue_list.currentRow()
        if row < 0:
            return
        w_item = self.queue_list.takeItem(row)
        if w_item is None:
            return
        item_id = w_item.data(Qt.ItemDataRole.UserRole)
        self.items = [it for it in self.items if it.id != item_id]
        self.item_map.pop(item_id, None)
        self.thumb_icons.pop(item_id, None)
        if not self.items:
            self.current_item_id = None
            self.current_image = None
            self.canvas.set_photo(None, [], self.config)
            self._refresh_face_list(None)
        self._update_ui_state()

    def _clear_all_items(self) -> None:
        if self._detect_worker is not None and self._detect_worker.isRunning():
            self._detect_worker.requestInterruption()
        self._pending_detect_ids.clear()
        self.items.clear()
        self.item_map.clear()
        self.thumb_icons.clear()
        self.queue_list.clear()
        self.current_item_id = None
        self.current_image = None
        self.canvas.set_photo(None, [], self.config)
        self._refresh_face_list(None)
        self.export_result_lbl.hide()
        self.queue_progress.hide()
        self.queue_progress_label.setText("대기 중인 작업 없음")
        self._update_ui_state()

    # ── Single & Batch Export ──────────────────────────────────────────
    def _export_current_photo(self) -> None:
        item = self._get_current_item()
        if item is None or self.current_image is None:
            return

        default_name = build_export_filename(item.display_name, self.export_format)
        start_dir = str(item.path.parent / default_name) if item.path else default_name
        filter_map = {
            "JPEG": "JPEG 이미지 (*.jpg)",
            "PNG": "PNG 이미지 (*.png)",
            "WEBP": "WebP 이미지 (*.webp)",
        }
        save_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "EXIF 없이 안전하게 저장",
            start_dir,
            filter_map[self.export_format],
        )
        if not save_path_str:
            return

        try:
            written_size, post_check = export_clean_image_file(
                self.current_image,
                item.faces,
                self.config,
                Path(save_path_str),
                self.export_format,
            )
            status = (
                f"✓ EXIF 0건 검증 완료 · {format_bytes(written_size)} 안전 저장됨"
                if not post_check.has_metadata
                else f"✓ {format_bytes(written_size)} 저장 완료"
            )
            self.export_result_lbl.setText(status)
            self.export_result_lbl.show()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "저장 실패", f"이미지 저장 중 오류: {exc}")

    def _export_all_photos(self) -> None:
        if not self.items:
            return
        if self._export_worker is not None and self._export_worker.isRunning():
            return

        ready_items = [it for it in self.items if it.status != "error"]
        if not ready_items:
            return

        out_dir_str = QFileDialog.getExistingDirectory(
            self,
            f"전체 {len(ready_items)}장을 일괄 저장할 폴더 선택",
        )
        if not out_dir_str:
            return

        self.export_progress.setRange(0, len(ready_items))
        self.export_progress.setValue(0)
        self.export_progress.show()
        self.export_result_lbl.hide()

        worker = BatchExportWorker(
            items=ready_items,
            config=self.config,
            output_dir=Path(out_dir_str),
            fmt=self.export_format,
        )
        worker.progress.connect(self._on_batch_export_progress)
        worker.finished_all.connect(self._on_batch_export_finished)
        worker.failed.connect(self._on_batch_export_failed)
        self._export_worker = worker
        worker.start()
        self._update_ui_state()

    def _on_batch_export_progress(self, done: int, total: int, filename: str) -> None:
        self.export_progress.setValue(done)
        self.queue_progress_label.setText(f"일괄 저장 중 ({done}/{total}): {filename}")

    def _on_batch_export_finished(
        self,
        saved_count: int,
        total_bytes: int,
        clean_exif_count: int,
        output_dir: str,
    ) -> None:
        self._export_worker = None
        self.export_progress.hide()
        self.queue_progress_label.setText(f"일괄 저장 완료 ({saved_count}장)")
        self.export_result_lbl.setText(
            f"✓ {saved_count}장 일괄 저장 완료 (EXIF 0건 검증 {clean_exif_count}/{saved_count}장 · 총 {format_bytes(total_bytes)})\n"
            f"저장 폴더: {output_dir}"
        )
        self.export_result_lbl.show()
        self._update_ui_state()

    def _on_batch_export_failed(self, error_msg: str) -> None:
        self._export_worker = None
        self.export_progress.hide()
        QMessageBox.critical(self, "일괄 저장 오류", error_msg)
        self._update_ui_state()

    # ── UI Sync & Drag-Drop / Keyboard Events ──────────────────────────
    def _set_show_original(self, show: bool) -> None:
        self.canvas.set_show_original(show)
        self.compare_btn.setProperty("active", show)
        self.compare_btn.style().unpolish(self.compare_btn)
        self.compare_btn.style().polish(self.compare_btn)

    def _update_ui_state(self) -> None:
        count = len(self.items)
        has_items = count > 0
        item = self._get_current_item()
        has_active = item is not None and self.current_image is not None
        is_exporting = self._export_worker is not None and self._export_worker.isRunning()
        is_detecting = self._detect_worker is not None and self._detect_worker.isRunning()

        self.queue_title.setText(f"사진 목록 ({count}장)")
        self.center_stack.setCurrentIndex(1 if has_items else 0)

        self.clear_queue_btn.setEnabled(has_items and not is_exporting)
        self.remove_item_btn.setEnabled(has_active and not is_exporting)
        self.redetect_all_btn.setEnabled(has_items and not is_detecting and not is_exporting)

        has_faces = item is not None and len(item.faces) > 0
        self.blur_all_btn.setEnabled(has_faces)
        self.unblur_all_btn.setEnabled(has_faces)
        self.draw_mode_btn.setEnabled(has_active)
        self.redetect_one_btn.setEnabled(has_active and not is_detecting)

        self.save_one_btn.setEnabled(has_active and not is_exporting)
        self.save_all_btn.setEnabled(has_items and not is_exporting and not is_detecting)
        self.save_all_btn.setText(f"전체 {count}장 폴더에 일괄 저장")

        if item is not None and item.width > 0:
            self.dim_badge.setText(f"{item.width}×{item.height}")
            if item.exif.has_metadata:
                tags_txt = ", ".join(item.exif.tags)
                self.exif_status_lbl.setObjectName("ExifDetected")
                self.exif_status_lbl.setText(
                    f"⚠ 원본 메타데이터 감지됨 ({tags_txt})\n저장 시 EXIF·위치정보가 100% 자동 삭제됩니다."
                )
            else:
                self.exif_status_lbl.setObjectName("ExifClean")
                self.exif_status_lbl.setText(
                    "✓ 원본 EXIF 없음 · 메타데이터 없이 깨끗하게 저장됩니다."
                )
        else:
            self.dim_badge.setText("-")
            self.exif_status_lbl.setObjectName("ExifClean")
            self.exif_status_lbl.setText("사진을 불러오면 EXIF 메타데이터를 자동 검사합니다.")

        self.exif_status_lbl.style().unpolish(self.exif_status_lbl)
        self.exif_status_lbl.style().polish(self.exif_status_lbl)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self.current_image is not None:
            self._set_show_original(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._set_show_original(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self.dropzone.setProperty("dragging", True)
            self.dropzone.style().unpolish(self.dropzone)
            self.dropzone.style().polish(self.dropzone)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: object) -> None:  # noqa: N802
        self.dropzone.setProperty("dragging", False)
        self.dropzone.style().unpolish(self.dropzone)
        self.dropzone.style().polish(self.dropzone)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.dropzone.setProperty("dragging", False)
        self.dropzone.style().unpolish(self.dropzone)
        self.dropzone.style().polish(self.dropzone)
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event: object) -> None:  # noqa: N802
        if self._detect_worker is not None and self._detect_worker.isRunning():
            self._detect_worker.requestInterruption()
            self._detect_worker.wait(2000)
        if self._export_worker is not None and self._export_worker.isRunning():
            self._export_worker.requestInterruption()
            self._export_worker.wait(2000)
        super().closeEvent(event)  # type: ignore[arg-type]
