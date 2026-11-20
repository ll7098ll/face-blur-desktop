# 얼굴블러 (FaceBlur Desktop)

100% 오프라인으로 동작하는 **Windows 네이티브 얼굴 자동 블러 & EXIF 메타데이터 삭제 데스크톱 앱**입니다.  
사진을 서버로 업로드하지 않고 내 PC 내부에서만 **InsightFace SCRFD(`det_10g.onnx`)** 모델로 얼굴을 정밀 감지하며, 여러 장의 사진을 동시에 불러와 클릭 한 번으로 원하는 얼굴만 남긴 뒤 EXIF·GPS 정보 없이 안전하게 저장할 수 있습니다.

---

## 주요 기능

- **고정밀 오프라인 얼굴 인식 (`SCRFD det_10g.onnx` + 멀티스케일 타일링)**
  - `onnxruntime` + `numpy` 기반의 경량 추론기로 동작하며, 정밀 감지 모드(기본 ON)에서는 전체 이미지 추론과 2×2 겹침 타일 추론을 결합해 배경 속 작은 얼굴·측면 얼굴까지 포착합니다.
- **여러 장 동시 일괄 처리 (배치 큐)**
  - 사진 여러 장 드래그 앤 드롭, 다중 파일 선택, 폴더 통째로 불러오기, 클립보드 붙여넣기(`Ctrl+V`)를 지원합니다.
  - 왼쪽 대기열에서 백그라운드로 순차 감지하며, **`전체 N장 폴더에 일괄 저장`**으로 한 번에 내보낼 수 있습니다.
- **클릭으로 개별 얼굴 블러 해제·재적용 & 수동 영역 추가**
  - 사진 위 얼굴 박스나 오른쪽 목록을 클릭해 특정 얼굴(예: 본인)만 원본으로 유지할 수 있습니다.
  - 인식이 빠진 영역은 `+ 직접 추가` 버튼으로 마우스 드래그해 수동 블러 박스를 추가할 수 있습니다.
- **EXIF 회전 자동 보정 & 메타데이터 0건 검증 저장**
  - 스마트폰 사진의 EXIF 회전 방향을 픽셀에 자동 반영(`exif_transpose`)한 뒤, 저장 시 메타데이터 없는 새 이미지로 인코딩하고 JPEG/PNG/WebP 바이너리를 재검사해 EXIF 0건을 검증합니다.
- **부드러운 블러 & 모자이크 + 밝은 화이트(Light) UI**
  - 페더링 타원 마스크 기반의 자연스러운 가우시안 블러와 모자이크 스타일, 강도·여백·민감도 조절 및 `Space` 키 원본 비교를 지원합니다.

---

## 프로젝트 구조

```text
├── app/
│   ├── main.py                 # 앱 진입점 (--smoke-test 지원)
│   ├── core/
│   │   ├── models.py           # Box, FaceRegion, BlurConfig, BatchItem 데이터 모델
│   │   ├── detector.py         # SCRFD ONNX 추론기, 2×2 타일링, IoU/IoS NMS
│   │   ├── blur.py             # 페더링 가우시안 블러, 모자이크, EXIF-free 내보내기
│   │   └── exif.py             # JPEG/PNG/WebP 바이너리 메타데이터 검사 & 회전 보정
│   └── ui/
│       ├── main_window.py      # 3단 화이트 스튜디오 메인 창 & 배치 큐 제어
│       ├── canvas_widget.py    # 인터랙티브 캔버스 (클릭 토글, 수동 드래그, 원본 비교)
│       ├── workers.py          # DetectionWorker / BatchExportWorker (QThread)
│       └── theme.py            # 밝은 화이트(Light) Qt 스타일시트
├── models/
│   └── det_10g.onnx            # InsightFace SCRFD 얼굴 감지 모델 (~16.9 MB)
├── tests/
│   └── test_core.py            # 단위 테스트 (EXIF, NMS, 블러 렌더링, SCRFD)
├── docs/
│   ├── ARCHITECTURE.md         # 기술 아키텍처 상세 문서
│   └── USER_GUIDE.md           # 사용자 가이드
├── build_exe.py                # PyInstaller 단일 실행 파일(얼굴블러.exe) 빌드 스크립트
├── pyproject.toml              # Python 3.12 프로젝트 설정 (uv)
└── uv.lock
```

---

## 설치 및 실행 방법

### 요구 사항
- **Python 3.12** (`>=3.12,<3.13`)
- **[uv](https://docs.astral.sh/uv/)** 패키지 매니저 (권장)

### 1. 의존성 설치 및 앱 실행
```powershell
uv sync --python 3.12
uv run python -m app.main
```

### 2. 테스트 실행
```powershell
uv run pytest -v
```

### 3. Windows 단독 실행 파일(`얼굴블러.exe`) 빌드
```powershell
uv run python build_exe.py
```
빌드가 완료되면 `dist/얼굴블러.exe` 및 프로젝트 루트의 `얼굴블러.exe`가 생성됩니다. `onnxruntime` DLL과 `models/det_10g.onnx`가 내부에 포함되어 있어 단일 파일만으로 실행할 수 있습니다.

---

## 상세 문서

- [아키텍처 문서 (ARCHITECTURE.md)](docs/ARCHITECTURE.md)
- [사용자 가이드 (USER_GUIDE.md)](docs/USER_GUIDE.md)

---

## 라이선스 및 모델 고지

- 애플리케이션 소스 코드는 [MIT License](LICENSE)를 따릅니다.
- 내장된 얼굴 감지 모델 `models/det_10g.onnx`는 [InsightFace](https://github.com/deepinsight/insightface) (`buffalo_l`)의 사전 학습 모델이며, 해당 모델 가중치의 라이선스 정책(비상업적 연구·개인 용도 등)을 준수합니다.
