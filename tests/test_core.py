from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.blur import (
    build_export_filename,
    compute_blur_radius,
    compute_mosaic_block_size,
    encode_clean_image_bytes,
    expand_and_clamp_box,
    export_clean_image_file,
    render_blurred_image,
)
from app.core.detector import (
    SCRFDDetector,
    generate_overlap_tiles,
    merge_detections_nms,
)
from app.core.exif import inspect_image_metadata, load_upright_rgb_image
from app.core.models import BlurConfig, Box, FaceRegion


def test_exif_inspector_jpeg_png_webp_and_malformed() -> None:
    jpeg_with_exif = bytes(
        [
            0xFF, 0xD8,
            0xFF, 0xE1, 0x00, 0x10,
            0x45, 0x78, 0x69, 0x66, 0x00, 0x00,
            0x4D, 0x4D, 0x00, 0x2A, 0x88, 0x25, 0x00, 0x00,
            0xFF, 0xDA, 0xFF, 0xD9,
        ]
    )
    res = inspect_image_metadata(jpeg_with_exif)
    assert res.has_metadata is True
    assert "EXIF (카메라·촬영정보)" in res.tags
    assert "GPS 위치태그 가능성" in res.tags

    clean_jpeg = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x06, 0x4A, 0x46, 0x49, 0x46, 0xFF, 0xDA, 0xFF, 0xD9])
    assert inspect_image_metadata(clean_jpeg).has_metadata is False

    png_with_exif = (
        b"\x89PNG\r\n\x1a\n"
        + (2).to_bytes(4, "big") + b"eXIf\x00\x00\x00\x00\x00\x00"
        + (0).to_bytes(4, "big") + b"IEND\x00\x00\x00\x00"
    )
    assert inspect_image_metadata(png_with_exif).has_metadata is True

    assert inspect_image_metadata(b"\xff\xd8\xff\xe1\x00\x00\xff\xff").has_metadata is False
    assert inspect_image_metadata(b"tiny").has_metadata is False


def test_nms_and_tile_generation() -> None:
    boxes = np.array(
        [
            [100.0, 100.0, 200.0, 200.0],  # high score main box
            [104.0, 98.0, 198.0, 202.0],   # overlapping duplicate from tile pass
            [120.0, 120.0, 180.0, 180.0],  # contained sub-box (high IoS)
            [400.0, 100.0, 480.0, 180.0],  # distinct second face
        ],
        dtype=np.float32,
    )
    scores = np.array([0.92, 0.85, 0.50, 0.88], dtype=np.float32)
    keep = merge_detections_nms(boxes, scores)
    assert keep == [0, 3]

    tiles = generate_overlap_tiles(1600, 1200, grid=2, overlap_ratio=0.15)
    assert len(tiles) == 4
    assert tiles[0][0] == 0 and tiles[0][1] == 0
    assert tiles[-1][2] == 1600 and tiles[-1][3] == 1200


def test_blur_math_and_rendering_modifies_only_blurred_faces() -> None:
    expanded = expand_and_clamp_box(Box(10, 15, 100, 100), 0.2, 200, 150)
    assert expanded.x == 0.0
    assert expanded.y == 0.0
    assert expanded.width == 130.0
    assert expanded.height == 135.0

    assert compute_blur_radius(Box(0, 0, 400, 400), 70) > compute_blur_radius(Box(0, 0, 60, 60), 70)
    assert compute_mosaic_block_size(Box(0, 0, 200, 200), 90) > compute_mosaic_block_size(Box(0, 0, 200, 200), 20)

    # Create high-contrast checkerboard image
    arr = np.zeros((200, 200, 3), dtype=np.uint8)
    arr[::2, ::2] = 255
    img = Image.fromarray(arr, mode="RGB")

    faces = [
        FaceRegion(id="f1", box=Box(20, 20, 60, 60), score=0.95, blurred=True),
        FaceRegion(id="f2", box=Box(120, 120, 60, 60), score=0.90, blurred=False),
    ]

    for style in ("gaussian", "mosaic"):
        cfg = BlurConfig(intensity=70, padding_ratio=0.1, style=style)
        out = render_blurred_image(img, faces, cfg)
        out_arr = np.asarray(out)
        # Blurred region center should differ from original sharp checkerboard
        assert not np.array_equal(out_arr[35:65, 35:65], arr[35:65, 35:65])
        # Unblurred face region should remain pixel-identical
        assert np.array_equal(out_arr[120:180, 120:180], arr[120:180, 120:180])


def test_exif_stripping_on_real_jpeg_export(tmp_path: Path) -> None:
    # Build a real JPEG containing EXIF metadata
    src = Image.new("RGB", (240, 180), color=(90, 140, 200))
    exif_obj = src.getexif()
    exif_obj[0x010F] = "TestCamera"
    buf = io.BytesIO()
    src.save(buf, format="JPEG", exif=exif_obj.tobytes())
    src_bytes = buf.getvalue()

    assert inspect_image_metadata(src_bytes).has_metadata is True

    upright = load_upright_rgb_image(src_bytes)
    out_bytes, post_check = encode_clean_image_bytes(upright, [], BlurConfig(), "JPEG")
    assert post_check.has_metadata is False
    assert inspect_image_metadata(out_bytes).has_metadata is False

    out_file = tmp_path / build_export_filename("trip.photo.JPG", "JPEG")
    assert out_file.name == "trip.photo_blurred.jpg"
    written_size, file_check = export_clean_image_file(upright, [], BlurConfig(), out_file, "JPEG")
    assert written_size > 0
    assert out_file.exists()
    assert file_check.has_metadata is False


def test_scrfd_detector_handles_blank_image_cleanly() -> None:
    detector = SCRFDDetector()
    blank = Image.new("RGB", (640, 480), color=(240, 240, 240))
    faces = detector.detect(blank, min_confidence=0.35, precision_mode=True)
    assert faces == []
