"""Miscellaneous tools - sync, profiles, version."""
from .base import T, ToolError, col


@T("sync", "Sync collection with AnkiWeb")
def sync():
    from aqt import mw
    auth = mw.pm.sync_auth()
    if not auth:
        raise ToolError("Not logged in to AnkiWeb", hint="Log in via Tools > Preferences > Sync")
    output = mw.col.sync_collection(auth, False)
    return {"status": "synced", "output": str(output)}


T("version", "Get Anki version", lambda: {"anki": col().sched_ver(), "mcp": "1.0.0"})

T("get-profiles", "List available profiles", lambda: __import__('aqt').mw.pm.profiles(), require_col=False)


@T("get-active-profile", "Get current profile name", require_col=False)
def get_active_profile():
    from aqt import mw
    return {"profile": mw.pm.name}


@T("reload-collection", "Reload the collection")
def reload_collection():
    from aqt import mw
    mw.col.close()
    mw.loadCollection()
    return {"reloaded": True}


@T("request-permission", "Request API permission", require_col=False)
def request_permission():
    return {"permission": "granted", "requireApiKey": False, "version": 6}


@T("api-reflect", "Get API reflection info", require_col=False)
def api_reflect(scopes: list[str] = None, actions: list[str] = None):
    from .base import _registry
    all_actions = list(_registry.keys())
    if actions:
        return {"scopes": scopes or [], "actions": {a: a in all_actions for a in actions}}
    return {"scopes": scopes or [], "actions": all_actions}


@T("load-profile", "Load a different profile", require_col=False)
def load_profile(name: str):
    from aqt import mw
    if name not in mw.pm.profiles():
        raise ToolError(f"Profile not found: {name}")
    mw.pm.load(name)
    mw.loadCollection()
    return {"loaded": name}


@T("multi", "Execute multiple actions")
def multi(actions: list[dict]):
    from ..handler_registry import execute
    results = []
    for a in actions:
        action = a.get("action")
        params = a.get("params", {})
        try:
            result = execute(action, params)
            results.append(result)
        except Exception as e:
            results.append({"error": str(e)})
    return {"results": results}
