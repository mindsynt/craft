"""
同步系统 — 移植自 packages/opencode/src/sync/
事件溯源 (Event Sourcing) 模式：事件定义、序列化、重放、投影
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from craft.config import CONFIG_DIR
from craft.core.id import ascending as id_ascending


# ── 事件注册表 ──────────────────────────────────────────────
# 对应 TS sync/index.ts 的 registry

_registry: dict[str, dict] = {}
_versions: dict[str, int] = {}
_projectors: dict[str, Callable] | None = None
_frozen = False


def versioned_type(type_name: str, version: int | None = None) -> str:
    """生成版本化的事件类型名"""
    return f"{type_name}.{version}" if version is not None else type_name


def define_event_sync(type_name: str, version: int, aggregate: str, schema: dict) -> dict:
    """定义同步事件类型

    Args:
        type_name: 事件类型名
        version: 版本号
        aggregate: 聚合根字段名
        schema: JSON schema dict

    Returns:
        事件定义 dict
    """
    if _frozen:
        raise RuntimeError("Error defining sync event: sync system has been frozen")

    definition = {
        "type": type_name,
        "version": version,
        "aggregate": aggregate,
        "schema": schema,
    }

    current_ver = _versions.get(type_name, 0)
    if version > current_ver:
        _versions[type_name] = version

    _registry[versioned_type(type_name, version)] = definition
    return definition


def init(projectors: list[tuple[dict, Callable]] | None = None):
    """初始化同步系统 — 注册投影器并冻结"""
    global _projectors, _frozen
    _projectors = dict(projectors) if projectors else {}
    _frozen = True


def reset():
    """重置同步系统（用于测试）"""
    global _frozen, _projectors
    _frozen = False
    _projectors = None


# ── 事件数据结构 ────────────────────────────────────────────

@dataclass
class SyncEvent:
    """同步事件实例"""
    id: str
    seq: int
    aggregate_id: str
    data: dict
    type: str = ""


@dataclass
class SerializedSyncEvent:
    """序列化后的同步事件"""
    id: str
    seq: int
    aggregate_id: str
    data: dict
    type: str


# ── 投影器 ──────────────────────────────────────────────────

class ProjectorRegistry:
    """投影器注册表"""

    def __init__(self):
        self._projectors: dict[str, Callable] = {}

    def register(self, event_type: str, projector: Callable):
        self._projectors[event_type] = projector

    def get(self, event_type: str) -> Callable | None:
        return self._projectors.get(event_type)


# ── 事件存储 ────────────────────────────────────────────────

class EventStore:
    """事件存储 — 简单的 JSON 文件存储

    对应 TS 的 SQLite EventTable/EventSequenceTable
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(CONFIG_DIR / "events.json")
        self._events: list[dict] = []
        self._sequences: dict[str, int] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._db_path):
                data = json.loads(Path(self._db_path).read_text())
                self._events = data.get("events", [])
                self._sequences = {s["aggregate_id"]: s["seq"] for s in data.get("sequences", [])}
            # Ensure integer seq values
            for k in self._sequences:
                self._sequences[k] = int(self._sequences[k])
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        Path(self._db_path).write_text(json.dumps({
            "events": self._events[-1000:],
            "sequences": [{"aggregate_id": k, "seq": v} for k, v in self._sequences.items()],
        }, indent=2, default=str))

    def append(self, event: SyncEvent):
        """追加事件"""
        self._events.append({
            "id": event.id,
            "seq": event.seq,
            "aggregate_id": event.aggregate_id,
            "type": event.type,
            "data": event.data,
        })
        self._sequences[event.aggregate_id] = event.seq
        self._save()

    def get_sequence(self, aggregate_id: str) -> int:
        """获取聚合根的最新序列号"""
        return self._sequences.get(aggregate_id, -1)

    def get_events(self, aggregate_id: str) -> list[dict]:
        """获取聚合根的所有事件"""
        return [e for e in self._events if e.get("aggregate_id") == aggregate_id]

    def remove_aggregate(self, aggregate_id: str):
        """删除聚合根的所有事件"""
        self._events = [e for e in self._events if e.get("aggregate_id") != aggregate_id]
        self._sequences.pop(aggregate_id, None)
        self._save()


# ── 同步管理器 ──────────────────────────────────────────────

class SyncManager:
    """同步管理器 — 事件溯源核心

    支持:
    - run: 运行事件（立即事务）
    - replay: 重放单个事件
    - replay_all: 重放全部事件
    - remove: 删除聚合根
    """

    def __init__(self, store: EventStore | None = None):
        self._store = store or EventStore()
        self._registry = ProjectorRegistry()

    def register_projector(self, event_type: str, projector: Callable):
        """注册投影器"""
        self._registry.register(event_type, projector)

    def run(self, defn: dict, data: dict, publish: bool = True):
        """运行事件 — 对应 TS SyncEvent.run

        Args:
            defn: 事件定义
            data: 事件数据
            publish: 是否通过总线发布
        """
        agg_key = defn.get("aggregate", "")
        agg_id = data.get(agg_key) if agg_key else data.get("id", str(uuid.uuid4()))

        if agg_id is None:
            raise ValueError(f'SyncEvent.run: "{agg_key}" required but not found')

        current_seq = self._store.get_sequence(agg_id)
        seq = current_seq + 1

        event = SyncEvent(
            id=id_ascending("event"),
            seq=seq,
            aggregate_id=agg_id,
            data=data,
            type=defn.get("type", ""),
        )

        # 运行投影器
        projector = self._registry.get(event.type)
        if projector:
            projector(event.data)

        # 持久化
        self._store.append(event)

        # 通过总线发布
        if publish:
            from craft.core.bus import bus
            bus.publish(f"sync.{event.type}", {
                "id": event.id,
                "seq": event.seq,
                "aggregateID": event.aggregate_id,
                "data": event.data,
            })

        return event

    def replay(self, serialized: SerializedSyncEvent, publish: bool = False):
        """重放单个事件 — 对应 TS SyncEvent.replay"""
        agg_id = serialized.aggregate_id
        current_seq = self._store.get_sequence(agg_id)

        if serialized.seq <= current_seq:
            return  # 幂等

        expected = current_seq + 1
        if serialized.seq != expected:
            raise ValueError(
                f'Sequence mismatch for aggregate "{agg_id}": '
                f'expected {expected}, got {serialized.seq}'
            )

        # 构造事件
        event = SyncEvent(
            id=serialized.id,
            seq=serialized.seq,
            aggregate_id=agg_id,
            data=serialized.data,
            type=serialized.type,
        )

        # 运行投影器
        projector = self._registry.get(event.type)
        if projector:
            projector(event.data)

        # 持久化
        self._store.append(event)

        if publish:
            from craft.core.bus import bus
            bus.publish(f"sync.{event.type}", {
                "id": event.id,
                "seq": event.seq,
                "aggregateID": event.aggregate_id,
                "data": event.data,
            })

    def replay_all(self, events: list[SerializedSyncEvent], publish: bool = False) -> str:
        """重放全部事件 — 对应 TS SyncEvent.replayAll"""
        if not events:
            raise ValueError("No events to replay")

        source = events[0].aggregate_id
        if any(e.aggregate_id != source for e in events):
            raise ValueError("Replay events must belong to the same session")

        start = events[0].seq
        for i, evt in enumerate(events):
            expected_seq = start + i
            if evt.seq != expected_seq:
                raise ValueError(f"Replay sequence mismatch at index {i}: expected {expected_seq}, got {evt.seq}")

        for evt in events:
            self.replay(evt, publish)

        return source

    def remove(self, aggregate_id: str):
        """删除聚合根 — 对应 TS SyncEvent.remove"""
        self._store.remove_aggregate(aggregate_id)


# ── 原有同步功能 ────────────────────────────────────────────

@dataclass
class SyncRecord:
    """键值同步记录"""
    key: str
    value: Any
    scope: str = "local"
    version: int = 0
    updated_at: float = 0.0

    def __post_init__(self):
        if not self.version:
            self.version = int(time.time() * 1000)
        if not self.updated_at:
            self.updated_at = time.time()


class KeyValueSync:
    """键值同步管理器"""

    def __init__(self):
        self._records: dict[str, SyncRecord] = {}
        self._db_path = CONFIG_DIR / "sync.json"
        self._load()

    def _load(self):
        try:
            if self._db_path.exists():
                data = json.loads(self._db_path.read_text())
                for item in data:
                    r = SyncRecord(**item)
                    self._records[r.key] = r
        except Exception:
            pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._db_path.write_text(json.dumps(
            [r.__dict__ for r in self._records.values()], indent=2, default=str
        ))

    def set(self, key: str, value: Any, scope: str = "local"):
        self._records[key] = SyncRecord(key=key, value=value, scope=scope)
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        r = self._records.get(key)
        return r.value if r else default

    def delete(self, key: str):
        self._records.pop(key, None)
        self._save()

    def list(self, scope: str | None = None) -> list[dict]:
        records = self._records.values()
        if scope:
            records = [r for r in records if r.scope == scope]
        return [{"key": r.key, "value": r.value, "scope": r.scope, "updated_at": r.updated_at}
                for r in records]


# ── 全局实例 ────────────────────────────────────────────────

from pathlib import Path as _Path
import os as _os


class CombinedSyncManager(SyncManager):
    """兼容原有接口的同步管理器

    保留 SyncManager 的事件溯源功能，同时兼容原始的 set/get API。
    """

    def __init__(self):
        super().__init__()
        self._kv = KeyValueSync()

    def set(self, key: str, value: Any, scope: str = "local"):
        """设置键值（兼容原有 API）"""
        self._kv.set(key, value, scope)

    def get(self, key: str, default: Any = None) -> Any:
        """获取键值（兼容原有 API）"""
        return self._kv.get(key, default)

    def delete(self, key: str):
        self._kv.delete(key)

    def list(self, scope: str | None = None) -> list[dict]:
        return self._kv.list(scope)


sync_manager = CombinedSyncManager()
key_value_sync = KeyValueSync()
