MEDIA_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF8": "image/gif",
    b"BM": "image/bmp",
    b"%PDF-": "application/pdf",
    b"RIFF": None,  # WEBP needs special handling
}


def is_pdf_attachment(mime: str) -> bool:
    """检查是否为 PDF — 移植自 media.ts isPdfAttachment"""
    return mime == "application/pdf"


def is_media(mime: str) -> bool:
    """检查是否为媒体 — 移植自 media.ts isMedia"""
    return mime.startswith("image/") or is_pdf_attachment(mime)


def is_image_attachment(mime: str) -> bool:
    """检查是否为图片附件 — 移植自 media.ts isImageAttachment"""
    return mime.startswith("image/") and mime not in ("image/svg+xml", "image/vnd.fastbidsheet")


def sniff_mime(data: bytes, fallback: str = "application/octet-stream") -> str:
    """嗅探 MIME 类型 — 移植自 media.ts sniffAttachmentMime"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback
