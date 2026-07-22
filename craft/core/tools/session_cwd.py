"""Per-session working directory (like cd in a terminal)."""


class SessionCwd:
    """Per-session working directory (like cd in a terminal)."""
    _store: dict[str, str] = {}
    _project_dir: str = "."

    @classmethod
    def init(cls, project_dir: str) -> None:
        cls._project_dir = project_dir

    @classmethod
    def get(cls, session_id: str) -> str:
        return cls._store.get(session_id, cls._project_dir)

    @classmethod
    def set(cls, session_id: str, directory: str) -> None:
        cls._store[session_id] = directory

    @classmethod
    def clear(cls, session_id: str) -> None:
        cls._store.pop(session_id, None)
