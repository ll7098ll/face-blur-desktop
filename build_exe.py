from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtSql",
    "PySide6.QtNetwork",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
    "PySide6.QtWebSockets",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtXml",
    "tkinter",
    "pytest",
]


def main() -> int:
    model_file = ROOT / "models" / "det_10g.onnx"
    if not model_file.exists():
        raise FileNotFoundError(f"Model file missing: {model_file}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "얼굴블러",
        "--add-data",
        f"{model_file};models",
        "--collect-binaries",
        "onnxruntime",
        "--hidden-import",
        "onnxruntime",
    ]
    for mod in EXCLUDES:
        cmd.extend(["--exclude-module", mod])

    cmd.append(str(ROOT / "app" / "main.py"))

    print("Building 얼굴블러.exe ...")
    subprocess.run(cmd, cwd=ROOT, check=True)

    dist_exe = ROOT / "dist" / "얼굴블러.exe"
    root_exe = ROOT / "얼굴블러.exe"
    shutil.copy2(dist_exe, root_exe)

    size_mb = root_exe.stat().st_size / (1024 * 1024)
    print(f"Build complete: {root_exe} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
