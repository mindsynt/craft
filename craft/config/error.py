"""配置错误类型 — 对应 error.ts"""


class ConfigJsonError(Exception):
    """JSON 解析错误"""

    def __init__(self, path: str, message: str | None = None):
        self.path = path
        self.message = message or f"Failed to parse config: {path}"
        super().__init__(self.message)


class ConfigInvalidError(Exception):
    """Schema 验证错误"""

    def __init__(self, path: str, issues: list[dict] | None = None, message: str | None = None):
        self.path = path
        self.issues = issues or []
        self.message = message or f"Invalid config: {path}"
        super().__init__(self.message)


class ConfigFrontmatterError(Exception):
    """Markdown frontmatter 解析错误"""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(message)
