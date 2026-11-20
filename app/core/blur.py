from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .exif import inspect_image_metadata
from .models import BlurConfig, Box, ExifInspection, ExportFormat, FaceRegion


FORMAT_EXT: dict[ExportFormat, str] = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


def expand_and_clamp_box(
    box: Box,
    padding_ratio: float,
    max_width: int,
    max_height: int,
) -> Box:
    pad_x = box.width * padding_ratio
    pad_y = box.height * padding_ratio
    x1 = max(0.0, box.x - pad_x)
    y1 = max(0.0, box.y - pad_y)
    x2 = min(float(max_width), box.x + box.width + pad_x)
    y2 = min(float(max_height), box.y + box.height + pad_y)
    return Box(
        x=x1,
        y=y1,
        width=max(0.0, x2 - x1),
        height=max(0.0, y2 - y1),
    )


def compute_blur_radius(box: Box, intensity: int) -> float:
    clamped = max(1, min(100, intensity))
    face_min = max(12.0, min(box.width, box.height))
    base = face_min * 0.22
    multiplier = 0.25 + (clamped / 100.0) * 1.5
    return max(2.0, min(90.0, base * multiplier))


def compute_mosaic_block_size(box: Box, intensity: int) -> int:
    clamped = max(1, min(100, intensity))
    face_min = max(12.0, min(box.width, box.height))
    divisions = max(4, round(18 - (clamped / 100.0) * 13))
    return max(4, round(face_min / divisions))


def build_export_filename(original_name: str, fmt: ExportFormat) -> str:
    stem = Path(original_name).stem.strip() or "photo"
    return f"{stem}_blurred{FORMAT_EXT[fmt]}"


def _create_feathered_ellipse_mask(width: int, height: int) -> Image.Image:
    ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
    xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    dist = np.sqrt(xs * xs + ys * ys)

    # Fully opaque up to 0.72 radius, smoothly feathered to 0 at 1.0
    alpha = np.clip((1.0 - dist) / (1.0 - 0.72), 0.0, 1.0)
    # Smoothstep curve for natural soft transition
    alpha = alpha * alpha * (3.0 - 2.0 * alpha)
    return Image.fromarray((alpha * 255.0).astype(np.uint8), mode="L")


def render_blurred_image(
    rgb_image: Image.Image,
    faces: list[FaceRegion],
    config: BlurConfig,
) -> Image.Image:
    """Return a copy of rgb_image with blurred/mosaic patches applied to enabled faces."""
    result = rgb_image.copy()
    img_w, img_h = result.size

    for face in faces:
        if not face.blurred:
            continue

        padded = expand_and_clamp_box(face.box, config.padding_ratio, img_w, img_h)
        rx = int(np.floor(padded.x))
        ry = int(np.floor(padded.y))
        rx2 = int(np.ceil(padded.x + padded.width))
        ry2 = int(np.ceil(padded.y + padded.height))
        rw = rx2 - rx
        rh = ry2 - ry
        if rw < 2 or rh < 2:
            continue

        mask = _create_feathered_ellipse_mask(rw, rh)

        if config.style == "mosaic":
            block = compute_mosaic_block_size(padded, config.intensity)
            tiny_w = max(1, round(rw / block))
            tiny_h = max(1, round(rh / block))
            patch = rgb_image.crop((rx, ry, rx2, ry2))
            mosaic = patch.resize((tiny_w, tiny_h), Image.Resampling.BILINEAR).resize(
                (rw, rh), Image.Resampling.NEAREST
            )
            result.paste(mosaic, (rx, ry), mask)
        else:
            radius = compute_blur_radius(padded, config.intensity)
            margin = int(np.ceil(radius * 2.2))
            cx1 = max(0, rx - margin)
            cy1 = max(0, ry - margin)
            cx2 = min(img_w, rx2 + margin)
            cy2 = min(img_h, ry2 + margin)

            crop_with_ctx = rgb_image.crop((cx1, cy1, cx2, cy2))
            blurred_ctx = crop_with_ctx.filter(ImageFilter.GaussianBlur(radius=radius))

            local_x1 = rx - cx1
            local_y1 = ry - cy1
            patch = blurred_ctx.crop((local_x1, local_y1, local_x1 + rw, local_y1 + rh))
            result.paste(patch, (rx, ry), mask)

    return result


def encode_clean_image_bytes(
    rgb_image: Image.Image,
    faces: list[FaceRegion],
    config: BlurConfig,
    fmt: ExportFormat,
    quality: int = 92,
) -> tuple[bytes, ExifInspection]:
    """Render blurred image into clean EXIF-free bytes and verify zero metadata."""
    rendered = render_blurred_image(rgb_image, faces, config)
    # Create fresh image buffer without carrying over any source .info/EXIF
    clean = Image.fromarray(np.asarray(rendered), mode="RGB")

    buf = io.BytesIO()
    if fmt == "PNG":
        clean.save(buf, format="PNG", optimize=True)
    elif fmt == "WEBP":
        clean.save(buf, format="WEBP", quality=quality, method=4)
    else:
        clean.save(buf, format="JPEG", quality=quality, subsampling=0)

    raw_bytes = buf.getvalue()
    post_check = inspect_image_metadata(raw_bytes)
    return raw_bytes, post_check


def export_clean_image_file(
    rgb_image: Image.Image,
    faces: list[FaceRegion],
    config: BlurConfig,
    output_path: Path,
    fmt: ExportFormat,
    quality: int = 92,
) -> tuple[int, ExifInspection]:
    raw_bytes, post_check = encode_clean_image_bytes(rgb_image, faces, config, fmt, quality)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw_bytes)
    return len(raw_bytes), post_check
