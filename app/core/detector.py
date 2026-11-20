from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from .models import Box, FaceRegion


def get_resource_path(relative_path: str) -> Path:
    """Resolve bundled asset paths for both dev runs and PyInstaller builds."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative_path
    return Path(__file__).resolve().parents[2] / relative_path


def compute_iou(box_a: np.ndarray, box_b: np.ndarray) -> float:
    xx1 = max(float(box_a[0]), float(box_b[0]))
    yy1 = max(float(box_a[1]), float(box_b[1]))
    xx2 = min(float(box_a[2]), float(box_b[2]))
    yy2 = min(float(box_a[3]), float(box_b[3]))
    inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, float(box_a[2] - box_a[0])) * max(0.0, float(box_a[3] - box_a[1]))
    area_b = max(0.0, float(box_b[2] - box_b[0])) * max(0.0, float(box_b[3] - box_b[1]))
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


def merge_detections_nms(
    boxes_xyxy: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float = 0.4,
    ios_threshold: float = 0.72,
) -> list[int]:
    """Suppress overlapping duplicate boxes using IoU and smaller-box containment (IoS)."""
    if len(scores) == 0:
        return []

    order = np.argsort(scores)[::-1]
    keep: list[int] = []

    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break

        rest = order[1:]
        xx1 = np.maximum(boxes_xyxy[i, 0], boxes_xyxy[rest, 0])
        yy1 = np.maximum(boxes_xyxy[i, 1], boxes_xyxy[rest, 1])
        xx2 = np.minimum(boxes_xyxy[i, 2], boxes_xyxy[rest, 2])
        yy2 = np.minimum(boxes_xyxy[i, 3], boxes_xyxy[rest, 3])

        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        area_i = max(0.0, boxes_xyxy[i, 2] - boxes_xyxy[i, 0]) * max(
            0.0, boxes_xyxy[i, 3] - boxes_xyxy[i, 1]
        )
        area_rest = np.maximum(0.0, boxes_xyxy[rest, 2] - boxes_xyxy[rest, 0]) * np.maximum(
            0.0, boxes_xyxy[rest, 3] - boxes_xyxy[rest, 1]
        )

        union = area_i + area_rest - inter
        iou = np.where(union > 0.0, inter / union, 0.0)

        min_area = np.minimum(area_i, area_rest)
        ios = np.where(min_area > 0.0, inter / min_area, 0.0)

        # Keep boxes that neither overlap strongly (IoU) nor sit mostly inside a higher-score box
        mask = (iou <= iou_threshold) & (ios <= ios_threshold)
        order = rest[mask]

    return keep


def generate_overlap_tiles(
    width: int,
    height: int,
    grid: int = 2,
    overlap_ratio: float = 0.15,
) -> list[tuple[int, int, int, int]]:
    """Generate (x1, y1, x2, y2) overlapping tiles covering the image."""
    tiles: list[tuple[int, int, int, int]] = []
    step_w = width / grid
    step_h = height / grid
    pad_w = int(round(step_w * overlap_ratio))
    pad_h = int(round(step_h * overlap_ratio))

    for gy in range(grid):
        for gx in range(grid):
            x1 = max(0, int(round(gx * step_w)) - pad_w)
            y1 = max(0, int(round(gy * step_h)) - pad_h)
            x2 = min(width, int(round((gx + 1) * step_w)) + pad_w)
            y2 = min(height, int(round((gy + 1) * step_h)) + pad_h)
            if x2 - x1 >= 32 and y2 - y1 >= 32:
                tiles.append((x1, y1, x2, y2))

    return tiles


class SCRFDDetector:
    """Offline InsightFace SCRFD (det_10g.onnx) detector using ONNX Runtime + NumPy."""

    _STRIDES = (8, 16, 32)
    _NUM_ANCHORS = 2

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or get_resource_path("models/det_10g.onnx")
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"얼굴 감지 모델 파일을 찾을 수 없습니다: {self.model_path}"
            )

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_opts.log_severity_level = 3
        cpu_count = os.cpu_count() or 4
        sess_opts.intra_op_num_threads = max(1, min(8, cpu_count))

        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self._center_cache: dict[tuple[int, int, int], np.ndarray] = {}

    def _get_anchor_centers(self, height: int, width: int, stride: int) -> np.ndarray:
        key = (height, width, stride)
        cached = self._center_cache.get(key)
        if cached is not None:
            return cached

        grid_y, grid_x = np.mgrid[:height, :width]
        centers = np.stack([grid_x, grid_y], axis=-1).astype(np.float32)
        centers = (centers * stride).reshape((-1, 2))
        if self._NUM_ANCHORS > 1:
            centers = np.stack([centers] * self._NUM_ANCHORS, axis=1).reshape((-1, 2))

        self._center_cache[key] = centers
        return centers

    def _detect_single_pass(
        self,
        rgb_image: Image.Image,
        input_size: int,
        min_confidence: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        orig_w, orig_h = rgb_image.size
        im_ratio = orig_h / float(orig_w)
        if im_ratio > 1.0:
            new_h = input_size
            new_w = max(1, int(round(new_h / im_ratio)))
        else:
            new_w = input_size
            new_h = max(1, int(round(new_w * im_ratio)))

        det_scale = new_h / float(orig_h)
        resized = rgb_image.resize((new_w, new_h), Image.Resampling.BILINEAR)

        canvas = np.zeros((input_size, input_size, 3), dtype=np.float32)
        canvas[:new_h, :new_w, :] = np.asarray(resized, dtype=np.float32)

        # SCRFD expects RGB normalized to [-1, 1] via (x - 127.5) / 128.0
        blob = (canvas - 127.5) / 128.0
        blob = np.transpose(blob, (2, 0, 1))[None, ...]

        outputs = self.session.run(self.output_names, {self.input_name: blob})
        fmc = len(self._STRIDES)

        boxes_list: list[np.ndarray] = []
        scores_list: list[np.ndarray] = []

        for idx, stride in enumerate(self._STRIDES):
            raw_scores = outputs[idx].reshape(-1)
            raw_bboxes = outputs[idx + fmc].reshape(-1, 4) * stride

            pos_inds = np.where(raw_scores >= min_confidence)[0]
            if pos_inds.size == 0:
                continue

            feat_h = input_size // stride
            feat_w = input_size // stride
            centers = self._get_anchor_centers(feat_h, feat_w, stride)

            sel_centers = centers[pos_inds]
            sel_dist = raw_bboxes[pos_inds]
            sel_scores = raw_scores[pos_inds]

            x1 = (sel_centers[:, 0] - sel_dist[:, 0]) / det_scale
            y1 = (sel_centers[:, 1] - sel_dist[:, 1]) / det_scale
            x2 = (sel_centers[:, 0] + sel_dist[:, 2]) / det_scale
            y2 = (sel_centers[:, 1] + sel_dist[:, 3]) / det_scale

            boxes = np.stack([x1, y1, x2, y2], axis=-1)
            boxes[:, 0] = np.clip(boxes[:, 0], 0.0, float(orig_w))
            boxes[:, 1] = np.clip(boxes[:, 1], 0.0, float(orig_h))
            boxes[:, 2] = np.clip(boxes[:, 2], 0.0, float(orig_w))
            boxes[:, 3] = np.clip(boxes[:, 3], 0.0, float(orig_h))

            boxes_list.append(boxes)
            scores_list.append(sel_scores)

        if not boxes_list:
            return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)

        return np.vstack(boxes_list), np.concatenate(scores_list)

    def detect(
        self,
        rgb_image: Image.Image,
        min_confidence: float = 0.35,
        precision_mode: bool = True,
    ) -> list[FaceRegion]:
        """Detect faces using SCRFD with optional 2x2 overlapping multi-scale tiling."""
        width, height = rgb_image.size
        all_boxes: list[np.ndarray] = []
        all_scores: list[np.ndarray] = []

        # Pass 1: Full image pass at native 640x640
        boxes, scores = self._detect_single_pass(rgb_image, 640, min_confidence)
        if len(scores) > 0:
            all_boxes.append(boxes)
            all_scores.append(scores)

        # Pass 2: 2x2 overlapping tiles at 640x640 (effective ~1150px+ detail) for small/distant faces
        if precision_mode and max(width, height) >= 800:
            for tx1, ty1, tx2, ty2 in generate_overlap_tiles(width, height, grid=2, overlap_ratio=0.15):
                tile = rgb_image.crop((tx1, ty1, tx2, ty2))
                t_boxes, t_scores = self._detect_single_pass(tile, 640, min_confidence)
                if len(t_scores) > 0:
                    t_boxes[:, [0, 2]] += tx1
                    t_boxes[:, [1, 3]] += ty1
                    all_boxes.append(t_boxes)
                    all_scores.append(t_scores)

        if not all_boxes:
            return []

        merged_boxes = np.vstack(all_boxes)
        merged_scores = np.concatenate(all_scores)
        keep_indices = merge_detections_nms(merged_boxes, merged_scores)

        regions: list[FaceRegion] = []
        for idx in keep_indices:
            x1, y1, x2, y2 = merged_boxes[idx]
            w = float(x2 - x1)
            h = float(y2 - y1)
            if w < 6.0 or h < 6.0:
                continue
            regions.append(
                FaceRegion(
                    id=f"face-{len(regions) + 1}-{int(round(x1))}-{int(round(y1))}",
                    box=Box(x=float(x1), y=float(y1), width=w, height=h),
                    score=float(merged_scores[idx]),
                    blurred=True,
                    source="auto",
                )
            )

        # Sort left-to-right, top-to-bottom for intuitive face numbering
        regions.sort(key=lambda r: (round(r.box.y / max(24.0, r.box.height * 0.45)), r.box.x))
        for i, reg in enumerate(regions, start=1):
            reg.id = f"face-{i}-{int(round(reg.box.x))}-{int(round(reg.box.y))}"

        return regions
