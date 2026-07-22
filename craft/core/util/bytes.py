def format_bytes(size: int) -> str:
    """格式化字节数"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f}{unit}" if isinstance(size, float) else f"{size}{unit}"
        size /= 1024
    return f"{size:.1f}PB"
