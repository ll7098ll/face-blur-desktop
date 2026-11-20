# 아키텍처 문서 (Architecture)

## 1. 설계 목표
1. **100% 오프라인 로컬 처리**: 모든 이미지 디코딩, 얼굴 추론, 블러 렌더링, EXIF 제거가 로컬 PC에서 실행됩니다.
2. **작은 얼굴·측면 얼굴 감지 강화**: 2-Pass 멀티스케일 타일링 + Cross-pass NMS로 원거리·군중 사진에서도 높은 재현율을 확보합니다.
3. **다중 이미지 메모리 최적화**: 대기열(`BatchItem`)에는 파일 경로, 감지된 얼굴 좌표, 96px 썸네일만 보관하고, 원본 고해상도 RGB 이미지는 현재 편집 중인 1장과 내보내기 시점에만 로드합니다.

---

## 2. 얼굴 감지 파이프라인 (`app/core/detector.py`)

```text
입력 RGB 이미지 (EXIF 회전 보정 완료)
   │
   ├──▶ Pass 1: 전체 이미지 레터박스 리사이즈 (640×640) ──▶ SCRFD 추론
   │
   └──▶ Pass 2 (정밀 모드 ON & max(w,h) >= 800):
           2×2 겹침 타일 (15% 오버랩) 각 640×640 ──────▶ SCRFD 추론
                                                               │
                                                               ▼
                                          Cross-pass NMS (IoU <= 0.4, IoS <= 0.72)
                                                               │
                                                               ▼
                                              좌→우 / 상→하 정렬된 FaceRegion 목록
```

- **순수 ONNX Runtime + NumPy 구현**: 무거운 외부 래퍼(`insightface`, `scipy`, `albumentations`) 없이 `onnxruntime`과 `numpy`만으로 앵커 중심 좌표(`strides = (8, 16, 32)`, `num_anchors = 2`)를 직접 디코딩합니다.
- **Cross-pass NMS**: 겹치는 타일 경계면 중복 박스를 `IoU`와 작은 박스 포함 비율(`IoS = intersection / min(area_a, area_b)`)로 함께 제거합니다.

---

## 3. 블러 렌더링 & EXIF 제거 (`app/core/blur.py`, `app/core/exif.py`)

1. **EXIF 회전 정규화**: `PIL.ImageOps.exif_transpose()`를 먼저 적용해 스마트폰 세로 촬영 사진의 픽셀 방향을 확정합니다.
2. **경계 번짐 없는 블러**:
   - **부드러운 블러**: 대상 얼굴 박스 주변에 `2.2 × radius` 여유 영역을 포함해 `GaussianBlur`를 적용한 뒤, Smoothstep 기반 페더링 타원 알파 마스크(`0.72 ~ 1.0` 구간 감쇠)로 합성해 테두리 경계선이나 외곽 어두워짐을 방지합니다.
   - **모자이크**: 얼굴 크기와 강도에 비례한 블록 크기로 다운스케일 후 `NEAREST` 업스케일합니다.
3. **EXIF 0건 검증**: `Image.fromarray(np.asarray(rendered), mode="RGB")`로 원본 `.info`나 EXIF 딕셔너리 없이 새 이미지를 인코딩한 뒤, `inspect_image_metadata()`로 JPEG(`APP1/APP13/COM`), PNG(`eXIf/tEXt/iTXt/zTXt`), WebP(`EXIF/XMP `) 청크가 0건인지 재확인합니다.

---

## 4. UI 및 비동기 워커 (`app/ui/`)

- `DetectionWorker(QThread)`: 대기열의 사진을 순차적으로 감지하고 완료될 때마다 썸네일 아이콘과 얼굴 수를 시그널로 전달합니다.
- `BatchExportWorker(QThread)`: 선택된 출력 폴더에 파일명 충돌을 피하면서(`_2`, `_3` 등) 전체 사진을 일괄 저장합니다.
- `PhotoCanvasWidget`: 위젯 좌표 ↔ 원본 이미지 좌표 역변환을 통해 리사이즈 시에도 정확한 클릭 토글과 수동 드래그 박스 추가를 지원합니다.
