# Model Weights License Notice (`det_10g.onnx`)

이 디렉터리에 포함된 `det_10g.onnx` 파일은 [InsightFace](https://github.com/deepinsight/insightface) 프로젝트의 **`buffalo_l` (SCRFD-10GF)** 사전 학습 얼굴 감지 모델 가중치입니다.

## 라이선스 구분

- **애플리케이션 소스 코드 (`app/`, `build_exe.py`, `tests/` 등)**: 루트의 [MIT License](../LICENSE)를 따릅니다.
- **사전 학습 모델 가중치 (`models/det_10g.onnx`)**: InsightFace 사전 학습 모델 정책에 따라 **비상업적 연구 및 개인 교육·연구 용도(Non-Commercial Research Purpose Only)**로만 사용할 수 있습니다.
  - 출처 및 상세 정책: <https://github.com/deepinsight/insightface#license>

## 실행 파일(`.exe`) 배포 시 유의사항

`build_exe.py`를 통해 생성되는 단일 실행 파일(`얼굴블러.exe`)은 내부에 `models/det_10g.onnx` 가중치를 번들로 포함합니다. 따라서 해당 모델이 포함된 실행 파일을 배포하거나 상업적 환경에서 사용할 경우 InsightFace 모델 가중치의 비상업적 라이선스 제한이 동일하게 적용됩니다. 상업적 용도로 활용하려면 상업적 사용이 허가된 별도의 ONNX 얼굴 감지 모델로 교체해야 합니다.
