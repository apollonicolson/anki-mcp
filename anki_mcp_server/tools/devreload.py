"""Hot reload - re-import tool modules without restarting Anki.

Dispatch is late-bound: request_processor calls handler_registry.execute(name, args),
which resolves the handler by name at call time, and the FastMCP wrapper only ever
passes the name. So repopulating the registry swaps in new code for existing tool
names immediately. New tool *names* still need the MCP server to re-advertise them.
"""
import importlib
import sys

from .base import T, ToolError


@T("reload-tools", "Re-import all tool modules in place, no Anki restart", require_col=False)
def reload_tools():
    from .. import handler_registry as hr

    pkg = __package__  # anki_mcp_server.tools
    before = sorted(hr._handlers)
    saved = dict(hr._handlers)

    hr._handlers.clear()
    purged = [m for m in list(sys.modules) if m == pkg or m.startswith(pkg + ".")]
    for name in purged:
        del sys.modules[name]

    try:
        importlib.import_module(pkg)
    except Exception as e:
        # Put the working registry back rather than leaving the server toolless.
        hr._handlers.clear()
        hr._handlers.update(saved)
        raise ToolError(f"Reload failed, previous handlers restored: {e}",
                        hint="Fix the syntax error and call reload-tools again")

    after = sorted(hr._handlers)

    # Re-advertise on the live FastMCP instance so new tool names become callable
    # and changed signatures/descriptions refresh, without restarting the server.
    from .. import mcp_server

    mcp = getattr(mcp_server, "_ACTIVE_MCP", None)
    call_main_thread = getattr(mcp_server, "_ACTIVE_CALL_MAIN_THREAD", None)
    advertised = None
    if mcp is not None and call_main_thread is not None:
        # add_tool returns the existing entry on a duplicate name, so stale schemas
        # would survive a plain re-register. Drop them all, then rebuild.
        for name in list(mcp._tool_manager._tools):
            mcp.remove_tool(name)
        new_base = importlib.import_module(pkg + ".base")
        new_base.register_tools(mcp, call_main_thread)
        advertised = len(mcp._tool_manager._tools)

    return {
        "modules_reloaded": len(purged),
        "handlers_before": len(before),
        "handlers_after": len(after),
        "advertised_tools": advertised,
        "added": [n for n in after if n not in saved],
        "removed": [n for n in before if n not in after],
        "note": ("tool list re-advertised in place" if advertised is not None
                 else "server instance not reachable; new names need an MCP reconnect"),
        "caveat": "the client may cache tools/list until it re-lists",
    }
