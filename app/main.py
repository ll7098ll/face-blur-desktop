from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.core.detector import SCRFDDetector
from app.ui.main_window import MainWindow
from app.ui.theme import LIGHT_THEME_QSS


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName("얼굴블러")
    app.setStyleSheet(LIGHT_THEME_QSS)

    detector = SCRFDDetector()
    window = MainWindow(detector=detector)

    if smoke_test:
        # Headless/offscreen verification hook for compiled executable
        window.resize(1280, 800)
        print("SMOKE_TEST_OK")
        return 0

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
