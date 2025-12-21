"""MCP Tool Framework - Progressive Disclosure Design.

Simple things simple, complex things possible.

## Level 1: One-liner (trivial tools)
    T("list-tags", "List all tags", lambda: col().tags.all())

## Level 2: Decorator (typed tools)
    @T("find-notes", "Search notes")
    def find_notes(query: str, limit: int = 100) -> dict:
        return {"noteIds": col().find_notes(query)[:limit]}

## Level 3: Full control (complex tools)
    @T("add-note", "Add a note", write=True)
    def add_note(deckName: str, modelName: str, fields: dict) -> dict:
        deck = col().decks.by_name(deckName)
        if not deck:
            raise ToolError(f"Deck not found: {deckName}", hint="Use list-decks")
        ...
"""
from typing import Any, Callable
from functools import wraps
import inspect
import logging

from ..handler_registry import register_handler

logger = logging.getLogger(__name__)

_registry: dict[str, dict] = {}


class ToolError(Exception):
    """Raise in handlers to return structured error responses."""
    def __init__(self, message: str, hint: str = None, **data):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.data = data


class T:
    """Universal tool definer with progressive disclosure.

    Adapts to how you use it:
    - T(name, desc, lambda: ...) -> one-liner
    - @T(name, desc) def fn(): ... -> decorator
    - T(name, desc, handler=fn, write=True) -> explicit config
    """

    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable = None,
        *,
        write: bool = False,
        require_col: bool = True,
        category: str = "essential",
    ):
        self.name = name
        self.description = description
        self.write = write
        self.require_col = require_col
        self.category = category

        if handler is not None:
            self._register(handler)

    def __call__(self, func: Callable) -> Callable:
        """Decorator mode: @T(name, desc) def fn(): ..."""
        self._register(func)
        return func

    def _register(self, func: Callable) -> None:
        """Register handler with all wrappers applied."""
        wrapped = func
        wrapped = _auto_response(wrapped)

        if self.write:
            wrapped = _write_lock(wrapped)

        if self.require_col:
            wrapped = _require_col(wrapped)

        wrapped = _error_handler(wrapped)
        wrapped.__signature__ = inspect.signature(func)
        wrapped.__annotations__ = getattr(func, '__annotations__', {})
        wrapped.__doc__ = func.__doc__

        register_handler(self.name, wrapped)
        _registry[self.name] = {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "handler": wrapped,
            "original": func,
        }


def _require_col(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        from aqt import mw
        if mw is None or mw.col is None:
            raise ToolError("Collection not loaded", hint="Open a profile in Anki first")
        return func(*args, **kwargs)
    return wrapper


def _write_lock(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        from aqt import mw
        try:
            mw.requireReset()
            return func(*args, **kwargs)
        finally:
            if mw and mw.col:
                mw.maybeReset()
    return wrapper


def _error_handler(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ToolError as e:
            result = {"success": False, "error": e.message, **e.data}
            if e.hint:
                result["hint"] = e.hint
            return result
        except Exception as e:
            logger.exception(f"Tool error: {e}")
            return {"success": False, "error": str(e)}
    return wrapper


def _auto_response(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, dict) and "success" in result:
            return result
        if result is None:
            return {"success": True}
        if isinstance(result, (list, tuple)):
            return {"success": True, "result": list(result)}
        if isinstance(result, dict):
            return {"success": True, **result}
        return {"success": True, "result": result}
    return wrapper


def register_tools(mcp, call_main_thread: Callable) -> None:
    """Register all T-defined tools with MCP server."""
    for name, meta in _registry.items():
        _make_mcp_tool(mcp, call_main_thread, name, meta)


def _make_mcp_tool(mcp, call_main_thread, name: str, meta: dict) -> None:
    original = meta["original"]
    sig = inspect.signature(original)

    async def wrapper(**kwargs):
        return await call_main_thread(name, kwargs)

    wrapper.__name__ = name
    wrapper.__doc__ = original.__doc__
    wrapper.__signature__ = sig
    wrapper.__annotations__ = getattr(original, '__annotations__', {}).copy()

    mcp.tool(description=meta["description"])(wrapper)


def col():
    """Get collection."""
    from aqt import mw
    return mw.col


def mw():
    """Get main window."""
    from aqt import mw as _mw
    return _mw
