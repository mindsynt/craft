# Craft 模块全面审计报告

## 审计方法

对应 MiMo-Code TypeScript 源文件（路径：`packages/opencode/src/cli/cmd/tui/` 和 `packages/opencode/src/`），逐一比对 Craft Python 实现的功能完整性。

**评级标准：**
- ✅ 功能完整 — 核心功能已实现，可正常工作
- ⚠️ 部分缺失 — 有基础实现但缺少关键功能或数据来源
- ❌ 空壳 — 文件存在但功能严重缺失（只有桩代码或硬编码占位）

---

## 1. craft/tui/ (TUI 层)

| 文件 | 状态 | TS 源 | 行数(Python→TS) | 问题 |
|------|------|-------|----------|------|
| `dialogs.py` | ❌ | `component/dialog-*.tsx` (30+个) + `ui/dialog-*.tsx` (7个) | 120→~15000+ | 只有4个基础对话框；缺失约25个复杂对话框，如dialog-mcp, dialog-agent, dialog-skill, dialog-session-list, dialog-session-rename, dialog-variant, dialog-tag, dialog-token-plan, dialog-modalities, dialog-logo-design, dialog-worktree, dialog-workflows 等 |
| `session_dialogs.py` | ❌ | `routes/session/*.tsx` | 55→~5000+ | 只有ForkDialog和MessageDialog两个小框架；缺失所有session路由组件 |
| `plugin_system.py` | ❌ | `feature-plugins/{home,sidebar,system}/` 多个文件 | 46→~3000+ | HomeSlot/SidebarSlot/SystemSlot 都是空占位，只显示静态标签 |
| `permission.py` | ❌ | `routes/session/permission.tsx` | 114→24792 | TS有730行，处理edit/read/glob/grep/bash/bash_delete/task/webfetch/websearch等12+种权限类型及diff渲染；Python只有硬编码对话框 |
| `session.py` | ⚠️ | `app.tsx` + 多个路由组件 | 289→~4000+ | 有基本聊天功能和命令处理，但相比TS完整app很简陋 |
| `components.py` | ⚠️ | `ui/*.tsx` + `component/*.tsx` (大量) | 183→~10000+ | 有基本Spinner/Toast/Confirm/Prompt/Select/Alert对话框，但TS有大量复杂组件缺失 |
| `sidebar_panels.py` | ⚠️ | `feature-plugins/sidebar/*.tsx` + `context/*.tsx` | 128→~6000+ | 有文件树/LSP/MCP/任务/TPS/目录/目标面板框架，但都是静态/硬编码数据 |
| `context.py` | ⚠️ | `context/*.tsx` (12个文件) | 93→~3000+ | 只有ThinkingIndicator/KeybindManager/ExitHandler；缺失context/theme.tsx, context/language.tsx, context/local.tsx, context/sync.tsx, context/keybind.tsx, context/prompt.tsx等 |
| `config_panel.py` | ⚠️ | `config/tui.ts` + `config/tui-schema.ts` | 58→~500+ | 有基本TUIConfig功能，可读写tui.json |
| `theme.py` | ⚠️ | `context/theme.tsx` + `theme/*.ts` | 115→~1000+ | 有4个主题和CSS生成，功能基本完整但只用了静态CSS而非动态 |
| `remaining.py` | ❌ | 多个零散TS源 | 132→~4000+ | 由7个框架级组件拼成（TipsWidget静态、QuestionPanel空壳、TimelineDialog模拟数据、SubagentDialog框架等） |
| `attach.py` | ⚠️ | `attach.ts` | 未详细检查 | |
| `event.py` | ⚠️ | `event.ts` | 未详细检查 | |
| `home.py` | ❌ | `feature-plugins/home/*.tsx` | 8行→~1000+ | 只有注释和import，无实际内容 |
| `layer.py` | ⚠️ | `layer.ts` | 未详细检查 | |
| `spinner.py` | ⚠️ | `ui/spinner.ts` | 未详细检查 | |
| `thread.py` | ⚠️ | `thread.ts` | 未详细检查 | |
| `tps.py` | ⚠️ | `feature-plugins/sidebar/tps.ts` | 未详细检查 | |
| `win32.py` | ⚠️ | `win32.ts` | 未详细检查 | |
| `worker.py` | ⚠️ | `worker.ts` | 未详细检查 | |

### `tui/` 子目录

| 文件 | 状态 | 说明 |
|------|------|------|
| `component/__init__.py` | ✅ | 空包文件 |
| `component/textarea_keybindings.py` | ⚠️ | 部分完整 |
| `component/prompt/` | ❌ | TS有prompt/index.tsx, stash.tsx, history.tsx, frecency.tsx, autocomplete.tsx 等复杂组件；Python只有基础框架 |
| `config/` (tui.py, tui_migrate.py, tui_schema.py) | ⚠️ | 部分完整 |
| `context/` (directory.py, event.py, plugin_keybinds.py, thinking.py) | ⚠️ | 都有基本实现但比TS少很多context类型 |
| `util/` (19个文件) | ✅ | **TUI中唯一较完整的子模块**。clipboard, editor, handoff, image_protocol, model, pinyin, provider_origin, revert_diff, scroll, selection, signal, sound, system_locale, terminal, transcript, vad, voice 基本都实现了对应TS功能 |
| `plugin/` (index.py, internal.py, runtime.py) | ✅ | 插件运行时基本完整 |

---

## 2. craft/core/server/routes/instance/ (API 路由层)

### 所有路由文件全面分析

| 文件 | 状态 | 说明 |
|------|------|------|
| `session.py` | ❌ | **严重空壳**。20个路由方法全部标注 `# TODO`，全部返回 `[]` 或 `{}`。0行真实功能代码 |
| `provider.py` | ❌ | 4个路由方法全部 `# TODO`，返回空字典 |
| `question.py` | ❌ | 5个路由方法全部 `# TODO`，返回空/False |
| `file.py` | ❌ | 6个路由方法全部 `# TODO`，返回 `[]` |
| `config.py` | ❌ | 3个路由方法全部 `# TODO`，返回 `{}` |
| `permission.py` | ❌ | 4个路由方法全部 `# TODO`，返回空/False |
| `mcp.py` | ❌ | 8个路由方法全部 `# TODO`，返回空字典 |
| `project.py` | ❌ | 4个路由方法全部 `# TODO`，返回 `[]` |
| `pty.py` | ❌ | 6个方法中5个 `# TODO`，只有connect_token有部分实现；connect方法抛出`NotImplementedError` |
| `bash_interactive.py` | ❌ | 2个方法全部 `# TODO` |
| `sync.py` | ❌ | 3个方法全部 `# TODO` |
| `experimental.py` | ❌ | 12个方法全部 `# TODO` |
| `workflows.py` | ❌ | 4个方法全部 `# TODO` |
| `tui.py` | ❌ | 11个方法全部返回 `True` 无实际逻辑 |
| `event.py` | ⚠️ | 只有基础SSE心跳，无事件总线集成 |
| `trace.py` | ✅ | 请求追踪工具函数全部实现 |
| `middleware.py` | ⚠️ | 实例中间件有基本目录解析实现 |
| `httpapi/server.py` | ❌ | 8行空壳类，标注 `TODO` |
| `httpapi/config.py` | ❌ | 剩 `pass` 的空类 |
| `httpapi/provider.py` | ❌ | 剩 `pass` 的空类 |
| `httpapi/permission.py` | ❌ | 剩 `pass` 的空类 |
| `httpapi/question.py` | ❌ | 剩 `pass` 的空类 |
| `httpapi/project.py` | ❌ | 剩 `pass` 的空类 |

**总结：craft/core/server/routes/ 目录总共 20+ 个 Python 文件，只有 `trace.py` 算是功能完整的。其余全部是空壳或极简桩。**

---

## 3. craft/core/session/prompt/ (Prompt 系统) ✅

| 文件 | 状态 | 说明 |
|------|------|------|
| `__init__.py` | ✅ | 包文档 |
| `empty_step_detection.py` | ✅ | 完整体现了 empty-step 检测逻辑 |
| `text_loop_recovery.py` | ✅ | 完整体现了 text loop 检测与恢复 |
| `text_ngram_detection.py` | ✅ | 有完整的 n-gram 重复检测和 TextNgramMonitor 类 |

**prompt/ 子模块是唯一完成度达到 100% 的模块。**

---

## 4. craft/cli/ (CLI 层)

| 文件 | 状态 | TS 源 | 说明 |
|------|------|-------|------|
| `bootstrap.py` | ⚠️ | `bootstrap.ts` | 有基本bootstrap骨架，但缺失真实项目初始化和错误处理 |
| `cmd.py` | ⚠️ | `cmd.ts` | CmdDef定义基类完整，但对比TS的type-safe命令系统很基础 |
| `debug.py` | ⚠️ | `debug/ripgrep.ts` + `debug/scrap.ts` | 有rg和scrap调试工具的基本实现 |
| `upgrade.py` | ⚠️ | `upgrade.ts` | 有版本检查和自动升级逻辑，但实际升级操作未实现 |
| `heap.py` | ✅ | `heap.ts` | 堆内存监控完整实现 |
| `logo.py` | ✅ | — | Craft CLI 标志 |

---

## 5. craft/core/plugin/ (插件系统) ✅

| 文件 | 状态 | 说明 |
|------|------|------|
| `__init__.py` | ✅ | 丰富的导出，显示模块结构完整 |
| `manager.py` | ✅ | PluginManager、Plugin、PluginHook 完整实现 |
| `hook_plugins.py` | ✅ | 子代理进度检查+检查点拆分插件完整实现 |
| `copilot.py` | ✅ | GitHub Copilot 认证+模型获取完整 |
| `debug_workspace.py` | ✅ | 调试工作区插件 |
| (cloudflare.py, xai.py, mimo.py, codex.py, install.py, matcher.py, meta.py, loader.py, shared.py) | ✅ | 全套插件支撑系统 |

---

## 总结

### ❌ 空壳文件（文件存在但功能严重缺失）：45+ 个

| 目录 | 文件 | 严重程度 |
|------|------|---------|
| `craft/tui/` | `dialogs.py`, `session_dialogs.py`, `plugin_system.py`, `permission.py`, `remaining.py`, `home.py` | 6个 |
| `craft/core/server/routes/instance/` | `session.py`, `provider.py`, `question.py`, `file.py`, `config.py`, `permission.py`, `mcp.py`, `project.py`, `pty.py`, `bash_interactive.py`, `sync.py`, `experimental.py`, `workflows.py`, `tui.py` | 14个 |
| `craft/core/server/routes/instance/httpapi/` | `server.py`, `config.py`, `provider.py`, `permission.py`, `question.py`, `project.py` | 6个 |
| `craft/core/server/` | `middleware.py` (部分), `event.py` (部分), `ui.py` (空壳) | 3个 |

### ⚠️ 部分缺失文件：20+ 个

| 目录 | 文件 |
|------|------|
| `craft/tui/` | `session.py`, `components.py`, `sidebar_panels.py`, `context.py`, `config_panel.py`, `theme.py`, `component/prompt/` |
| `craft/cli/` | `bootstrap.py`, `cmd.py`, `debug.py`, `upgrade.py` |

### ✅ 功能完整模块：~30 个文件

| 目录 | 文件 |
|------|------|
| `craft/tui/util/` | (19个工具文件) |
| `craft/core/session/prompt/` | (4个文件) |
| `craft/core/plugin/` | (10+个文件) |
| `craft/cli/` | `heap.py`, `logo.py` |

### 核心结论

1. **TUI 层完成度大约 30%** — 对话框系统严重缺失(30+ TS 对话框仅移植4个)，权限审批只有框架，侧栏面板只有显示层无数据绑定
2. **API 路由层几乎 100% 是空壳** — 所有路由方法都标注了 `# TODO`，返回空数据。这层需要从零开始实现
3. **Prompt 检测系统完成度 100%** — 这是唯一完全移植的子模块
4. **插件系统完成度 ~85%** — 框架完整，具体插件实现度较好
5. **CLI 工具完成度 ~50%** — 基本框架有，但真正常用的命令还需要大量工作
