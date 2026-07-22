import base64


def decode_data_url(url: str) -> str:
    """解码 data URL — 移植自 data-url.ts decodeDataUrl"""
    idx = url.find(",")
    if idx == -1:
        return ""
    head = url[:idx]
    body = url[idx + 1:]
    if ";base64" in head:
        return base64.b64decode(body).decode("utf-8", errors="replace")
    from urllib.parse import unquote
    return unquote(body)
