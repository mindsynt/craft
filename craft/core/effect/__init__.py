"""
Effect 适配 — 包装为 craft.core.effect 包

移植自 packages/opencode/src/effect/
Effect-TS 的 Python 等价模式

移植文件清单 (14 个 TS → Python):
  - index.ts
  - instance-state.ts      → InstanceState
  - bootstrap-runtime.ts   → BootstrapRuntime
  - instance-ref.ts        → InstanceRef / WorkspaceRef
  - instance-registry.ts   → InstanceRegistry (disposers)
  - runtime.ts             → Runtime
  - logger.ts              → EffectLogger
  - observability.ts       → Observability
  - bridge.ts              → EffectBridge
  - cross-spawn-spawner.ts → CrossSpawnSpawner
  - runner.ts              → Runner
  - run-service.ts         → RunService
  - app-runtime.ts         → AppRuntime
  - memo-map.ts            → MemoMap
"""

from .core import *
from .instance_state import *
from .memo_map import *
from .logger import *
from .observability import *
from .runner import *
from .bridge import *
from .runtime import *
from .run_service import *
from .spawner import *
from .bootstrap_runtime import *
from .app_runtime import *
