LIGHT_THEME_QSS = """
QMainWindow, QWidget {
    background-color: #F8FAFC;
    color: #0F172A;
    font-family: "Malgun Gothic", "Segoe UI", sans-serif;
    font-size: 13px;
}

QFrame#TopBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
}

QLabel#BrandTitle {
    font-size: 18px;
    font-weight: 700;
    color: #0F172A;
    background: transparent;
}

QLabel#BrandSub {
    font-size: 12px;
    color: #64748B;
    background: transparent;
}

QLabel#PrivacyPill {
    background-color: #ECFDF5;
    color: #047857;
    border: 1px solid #A7F3D0;
    border-radius: 14px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}

QFrame#Card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}

QFrame#CanvasCard {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
}

QFrame#DropZone {
    background-color: #FFFFFF;
    border: 2px dashed #CBD5E1;
    border-radius: 18px;
}

QFrame#DropZone[dragging="true"] {
    background-color: #EFF6FF;
    border: 2px dashed #2563EB;
}

QLabel#SectionTitle {
    font-size: 13px;
    font-weight: 700;
    color: #0F172A;
    background: transparent;
}

QLabel#MutedText {
    font-size: 12px;
    color: #64748B;
    background: transparent;
}

QLabel#CountBadge {
    background-color: #F1F5F9;
    color: #334155;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#ExifClean {
    background-color: #ECFDF5;
    color: #065F46;
    border: 1px solid #A7F3D0;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
}

QLabel#ExifDetected {
    background-color: #FFFBEB;
    color: #92400E;
    border: 1px solid #FDE68A;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
}

QLabel#ExportSuccess {
    background-color: #ECFDF5;
    color: #047857;
    border: 1px solid #A7F3D0;
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 7px 12px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}

QPushButton:pressed {
    background-color: #E2E8F0;
}

QPushButton:disabled {
    background-color: #F8FAFC;
    color: #94A3B8;
    border-color: #E2E8F0;
}

QPushButton#PrimaryBtn {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
    padding: 9px 14px;
}

QPushButton#PrimaryBtn:hover {
    background-color: #1D4ED8;
}

QPushButton#PrimaryBtn:pressed {
    background-color: #1E40AF;
}

QPushButton#PrimaryBtn:disabled {
    background-color: #93C5FD;
    border-color: #93C5FD;
    color: #EFF6FF;
}

QPushButton#BatchBtn {
    background-color: #0F172A;
    color: #FFFFFF;
    border: 1px solid #0F172A;
    padding: 9px 14px;
}

QPushButton#BatchBtn:hover {
    background-color: #1E293B;
}

QPushButton#BatchBtn:disabled {
    background-color: #CBD5E1;
    border-color: #CBD5E1;
    color: #FFFFFF;
}

QPushButton[active="true"] {
    background-color: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #3B82F6;
}

QPushButton#SmallChip {
    padding: 5px 8px;
    font-size: 12px;
    border-radius: 7px;
}

QListWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    outline: none;
    padding: 4px;
}

QListWidget::item {
    border-radius: 8px;
    padding: 6px;
    margin-bottom: 3px;
    color: #0F172A;
}

QListWidget::item:hover {
    background-color: #F1F5F9;
}

QListWidget::item:selected {
    background-color: #EFF6FF;
    color: #1E3A8A;
    border: 1px solid #93C5FD;
}

QComboBox {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 6px 10px;
}

QComboBox:hover {
    border-color: #94A3B8;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #0F172A;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    border: 1px solid #CBD5E1;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #E2E8F0;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #2563EB;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 2px solid #2563EB;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 8px;
}

QCheckBox {
    spacing: 7px;
    color: #334155;
    background: transparent;
}

QProgressBar {
    background-color: #E2E8F0;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #2563EB;
    border-radius: 4px;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
