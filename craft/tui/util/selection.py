"""
选择 — 移植自 util/selection.ts

从编辑器渲染器获取选中文本并复制到剪贴板。
"""

from __future__ import annotations

from craft.tui.util import clipboard as _clipboard


def copy_selection(renderer, toast, message: str) -> bool:
    """复制编辑器选中文本到剪贴板"""
    try:
        selection = getattr(renderer, "get_selection", lambda: None)()
        if selection is None:
            return False
        text = getattr(selection, "get_selected_text", lambda: "")()
        if not text:
            return False
        _clipboard.copy(text)
        toast.show(message=message, variant="info")
        renderer.clear_selection()
        return True
    except Exception:
        return False
