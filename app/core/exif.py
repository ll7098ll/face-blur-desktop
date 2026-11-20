from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from .models import ExifInspection


def _inspect_jpeg(data: bytes) -> ExifInspection:
    tags: list[str] = []
    seen: set[str] = set()
    offset = 2  # Skip SOI (FF D8)
    n = len(data)

    def add(tag: str) -> None:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    while offset + 4 <= n:
        if data[offset] != 0xFF:
            break
        while offset < n and data[offset] == 0xFF:
            offset += 1
        if offset >= n:
            break

        marker = data[offset]
        offset += 1

        if marker in (0xDA, 0xD9):  # SOS or EOI
            break
        if marker == 0x01 or (0xD0 <= marker <= 0xD7):
            continue

        if offset + 2 > n:
            break
        seg_len = (data[offset] << 8) | data[offset + 1]
        if seg_len < 2:
            break

        payload_start = offset + 2
        payload_end = min(n, offset + seg_len)
        payload = data[payload_start:payload_end]

        if marker == 0xE1:
            if payload.startswith(b"Exif\x00\x00"):
                add("EXIF (카메라·촬영정보)")
                if b"\x88\x25" in payload or b"\x25\x88" in payload:
                    add("GPS 위치태그 가능성")
            elif b"http://ns.adobe.com/xap/" in payload[:64]:
                add("XMP 메타데이터")
            else:
                add("APP1 메타데이터")
        elif marker == 0xED:
            add("IPTC 정보")
        elif marker == 0xFE:
            add("JPEG 코멘트")

        offset += seg_len

    return ExifInspection(has_metadata=len(tags) > 0, tags=tags)


def _inspect_png(data: bytes) -> ExifInspection:
    tags: list[str] = []
    seen: set[str] = set()
    offset = 8
    n = len(data)

    def add(tag: str) -> None:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    while offset + 12 <= n:
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        if chunk_type == b"eXIf":
            add("EXIF 청크")
        elif chunk_type in (b"tEXt", b"iTXt", b"zTXt"):
            add("텍스트/XMP 메타데이터")
        if chunk_type == b"IEND":
            break
        nxt = offset + 12 + length
        if nxt <= offset:
            break
        offset = nxt

    return ExifInspection(has_metadata=len(tags) > 0, tags=tags)


def _inspect_webp(data: bytes) -> ExifInspection:
    tags: list[str] = []
    seen: set[str] = set()
    offset = 12
    n = len(data)

    def add(tag: str) -> None:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    while offset + 8 <= n:
        fourcc = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        if fourcc == b"EXIF":
            add("EXIF 청크")
        elif fourcc == b"XMP ":
            add("XMP 메타데이터")
        padded = size + (size % 2)
        nxt = offset + 8 + padded
        if nxt <= offset:
            break
        offset = nxt

    return ExifInspection(has_metadata=len(tags) > 0, tags=tags)


def inspect_image_metadata(data: bytes) -> ExifInspection:
    """Inspect JPEG, PNG, or WebP raw bytes for EXIF/XMP/IPTC metadata."""
    if len(data) < 12:
        return ExifInspection(False, [])
    if data[:2] == b"\xff\xd8":
        return _inspect_jpeg(data)
    if data[:4] == b"\x89PNG":
        return _inspect_png(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _inspect_webp(data)
    return ExifInspection(False, [])


def load_upright_rgb_image(source: Path | bytes) -> Image.Image:
    """Load an image, apply EXIF orientation into upright pixels, and return RGB."""
    if isinstance(source, bytes):
        with Image.open(io.BytesIO(source)) as img:
            upright = ImageOps.exif_transpose(img)
            return upright.convert("RGB")
    with Image.open(source) as img:
        upright = ImageOps.exif_transpose(img)
        return upright.convert("RGB")
