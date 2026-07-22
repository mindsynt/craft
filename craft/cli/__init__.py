"""
Craft CLI — 移植自 MiMo-Code packages/opencode/src/cli/

包含：bootstrap, cmd helper, debug commands, heap, upgrade, logo,
以及补充的命令模块（agent, db, serve, providers, models, session）
"""

from __future__ import annotations

from craft.cli.agent_cmd import (
    handle_agent_create,
    handle_agent_generate,
    handle_agent_list,
    handle_agent_show,
)
from craft.cli.bootstrap import bootstrap
from craft.cli.cmd import CmdDef, cmd, get_cmd_def
from craft.cli.db_cmd import (
    handle_db_path,
    handle_db_query,
)
from craft.cli.debug import (
    RipgrepCommand,
    ScrapCommand,
    rg_files,
    rg_search,
    rg_tree,
    scrap_projects,
)
from craft.cli.heap import start as heap_start
from craft.cli.logo import LogoLines, go_logo, logo, logo_thin, logos, marks
from craft.cli.models_cmd import handle_models_list
from craft.cli.providers_cmd import (
    handle_providers_add,
    handle_providers_list,
    handle_providers_remove,
)
from craft.cli.serve_cmd import handle_serve
from craft.cli.session_cmd import (
    handle_session_delete,
    handle_session_list,
    handle_session_show,
)
from craft.cli.upgrade import upgrade

__all__ = [
    "bootstrap",
    "CmdDef",
    "cmd",
    "get_cmd_def",
    # agent
    "handle_agent_create",
    "handle_agent_list",
    "handle_agent_show",
    "handle_agent_generate",
    # db
    "handle_db_query",
    "handle_db_path",
    # serve
    "handle_serve",
    # providers
    "handle_providers_list",
    "handle_providers_add",
    "handle_providers_remove",
    # models
    "handle_models_list",
    # session
    "handle_session_list",
    "handle_session_show",
    "handle_session_delete",
    # debug
    "RipgrepCommand",
    "ScrapCommand",
    "rg_files",
    "rg_search",
    "rg_tree",
    "scrap_projects",
    # utility
    "heap_start",
    "upgrade",
    "logo",
    "logo_thin",
    "logos",
    "go_logo",
    "marks",
    "LogoLines",
]
