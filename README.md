# Craft — MiMo-Code Python 移植版本

## 完成状态

| 模块 | 源文件 (MiMo-Code TS) | 移植 (Python) | 状态 |
|------|----------------------|--------------|------|
| config/ | 1089 行 config.ts | craft/config.py | ✅ |
| provider/ | packages/opencode/src/provider/ | craft/core/provider.py | ✅ |
| agent/ | 613 行 agent.ts | craft/core/agent.py | ✅ |
| memory/ | 144 行 memory/service.ts | craft/core/memory.py | ✅ |
| tool/ | packages/opencode/src/tool/ | craft/core/tools.py | ✅ |
| session/ | packages/opencode/src/session/ | craft/core/session.py | ✅ |
| auth/ | packages/opencode/src/auth/ | craft/core/auth.py | ✅ |
| permission/ | packages/opencode/src/permission/ | craft/core/permission.py | ✅ |
| CLI | packages/console/ (199 文件) | craft/cli/__init__.py | ✅ |
| API | packages/app/ + packages/web/ | craft/api/server.py | ✅ |
| Web UI | packages/web/ (SolidJS) | Next.js web/ | ✅ |

## 运行

```bash
# CLI
craft chat

# API
craft serve

# Web UI
cd web && bun dev
```

## 测试结果

全部 API 端点通过测试 ✅
Web 前端构建成功 ✅
CLI 所有命令可用 ✅
