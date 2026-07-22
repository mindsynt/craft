"""定时任务系统 — 包结构

移植自 packages/opencode/src/cron/
基于 asyncio 的轻量调度器，支持 cron 表达式、一次性、重复任务
"""

from __future__ import annotations

from craft.core.cron.expr import (
    CronFields,
    FIELD_RANGES,
    parse_cron_expression,
    compute_next_cron_run,
    cron_to_human,
)
from craft.core.cron.jitter import (
    JitterConfig,
    DEFAULT_JITTER,
    jittered_next_cron_run_ms,
    one_shot_jittered_next_cron_run_ms,
)
from craft.core.cron.lock import (
    LockInfo,
    PROC_STARTED_AT,
    get_lock_file_path,
    try_acquire_scheduler_lock,
    release_scheduler_lock,
)
from craft.core.cron.task import (
    CRON_TASKS_DIR,
    CRON_TASKS_FILE,
    read_cron_tasks,
    write_cron_tasks,
    add_session_cron_task,
    get_session_cron_tasks,
    remove_session_cron_tasks,
    find_missed_tasks,
    mark_cron_tasks_fired,
)
from craft.core.cron.loop import (
    MAX_LOOP_FILE_BYTES,
    read_loop_file,
    LoopState,
    get_loop_state,
    set_loop_state,
    delete_loop_state,
    list_loop_states,
    clear_all_loop_states,
    reset_strikes,
    increment_strikes,
    get_strikes,
)
from craft.core.cron.sentinel import (
    SENTINELS,
    LOOP_FILE_SENTINEL,
    LOOP_FILE_DYNAMIC_SENTINEL,
    AUTONOMOUS_LOOP_SENTINEL,
    AUTONOMOUS_LOOP_DYNAMIC_SENTINEL,
    AUTONOMOUS_LOOP_PREAMBLE,
    AUTONOMOUS_LOOP_SHORT_REMINDER,
    LOOP_FILE_ABSENT_REMINDER,
    LOOP_FILE_UNCHANGED_REMINDER,
    is_sentinel,
    resolve_at_fire_time,
    reset_on_compaction,
)
from craft.core.cron.scheduler import (
    CronJob,
    CronParser,
    LoopEndedReason,
    LoopEndedEvent,
    StartOpts,
    NewCronTask,
    ArmLoopInput,
    ArmLoopResult,
    SchedulerInterface,
    EnhancedScheduler,
    CronScheduler,
    scheduler,
    enhanced_scheduler,
)

__all__ = [
    "CronFields", "FIELD_RANGES", "parse_cron_expression",
    "compute_next_cron_run", "cron_to_human",
    "JitterConfig", "DEFAULT_JITTER",
    "jittered_next_cron_run_ms", "one_shot_jittered_next_cron_run_ms",
    "LockInfo", "PROC_STARTED_AT", "get_lock_file_path",
    "try_acquire_scheduler_lock", "release_scheduler_lock",
    "CRON_TASKS_DIR", "CRON_TASKS_FILE",
    "read_cron_tasks", "write_cron_tasks",
    "add_session_cron_task", "get_session_cron_tasks",
    "remove_session_cron_tasks", "find_missed_tasks",
    "mark_cron_tasks_fired",
    "MAX_LOOP_FILE_BYTES", "read_loop_file",
    "LoopState", "get_loop_state", "set_loop_state",
    "delete_loop_state", "list_loop_states", "clear_all_loop_states",
    "reset_strikes", "increment_strikes", "get_strikes",
    "SENTINELS", "LOOP_FILE_SENTINEL", "LOOP_FILE_DYNAMIC_SENTINEL",
    "AUTONOMOUS_LOOP_SENTINEL", "AUTONOMOUS_LOOP_DYNAMIC_SENTINEL",
    "AUTONOMOUS_LOOP_PREAMBLE", "AUTONOMOUS_LOOP_SHORT_REMINDER",
    "LOOP_FILE_ABSENT_REMINDER", "LOOP_FILE_UNCHANGED_REMINDER",
    "is_sentinel", "resolve_at_fire_time", "reset_on_compaction",
    "CronJob", "CronParser",
    "LoopEndedReason", "LoopEndedEvent",
    "StartOpts", "NewCronTask", "ArmLoopInput", "ArmLoopResult",
    "SchedulerInterface", "EnhancedScheduler", "CronScheduler",
    "scheduler", "enhanced_scheduler",
]
