"""Image compression utilities — ported from image.ts"""

from __future__ import annotations

import base64

DEFAULT_MAX_IMAGE_BYTES = 4_500_000


def compress_image(
    data: bytes,
    media_type: str = "image/jpeg",
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    format: str = "JPEG",
) -> tuple[str, str] | None:
    """
    Compress an image to fit within max_bytes.
    Returns (base64_data, media_type) or None if compression fails.
    Port of compressImage from image.ts
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        return None

    try:
        img = Image.open(io.BytesIO(data))
    except Exception:
        return None

    # Try progressively lower quality, then smaller dimensions
    scales = [1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1]
    qualities = [85, 65, 45, 30]

    for scale in scales:
        if scale < 1.0:
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            scaled = img.resize((w, h), Image.LANCZOS)
        else:
            scaled = img

        for quality in qualities:
            buf = io.BytesIO()
            try:
                scaled.save(buf, format=format, quality=quality)
                if buf.tell() <= max_bytes:
                    return (
                        base64.b64encode(buf.getvalue()).decode("ascii"),
                        f"image/{format.lower()}",
                    )
            except Exception:
                continue

    return None
