def get_system_locale() -> str:
    """获取系统语言"""
    import locale
    try:
        return locale.getdefaultlocale()[0] or "en_US"
    except Exception:
        return "en_US"
