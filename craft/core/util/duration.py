def format_duration(seconds: float) -> str:
    """格式化时长（秒）"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds//60:.0f}m{seconds%60:.0f}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h:.0f}h{m:.0f}m"


def format_duration_precise(seconds: float) -> str:
    """精确格式化时长 — 移植自 format.ts formatDuration"""
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        mins = int(seconds // 60)
        remaining = seconds % 60
        return f"{mins}m {remaining}s" if remaining > 0 else f"{mins}m"
    if seconds < 86400:
        hours = int(seconds // 3600)
        remaining = int((seconds % 3600) // 60)
        return f"{hours}h {remaining}m" if remaining > 0 else f"{hours}h"
    if seconds < 604800:
        days = int(seconds // 86400)
        return "~1 day" if days == 1 else f"~{days} days"
    weeks = int(seconds // 604800)
    return "~1 week" if weeks == 1 else f"~{weeks} weeks"


def format_ms(millis: float) -> str:
    """格式化毫秒数 — 移植自 locale.ts duration"""
    if millis < 1000:
        return f"{millis:.0f}ms"
    if millis < 60000:
        return f"{millis / 1000:.1f}s"
    if millis < 3600000:
        minutes = int(millis // 60000)
        seconds = int((millis % 60000) // 1000)
        return f"{minutes}m {seconds}s"
    if millis < 86400000:
        hours = int(millis // 3600000)
        minutes = int((millis % 3600000) // 60000)
        return f"{hours}h {minutes}m"
    hours = int(millis // 3600000)
    days = int((millis % 3600000) // 86400000)
    return f"{days}d {hours}h"
