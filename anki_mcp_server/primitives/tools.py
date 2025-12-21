# primitives/tools.py
"""Central tool registration module."""

from typing import Any, Callable, Coroutine

# Import all essential tools (this triggers handler registration at import time)
from .essential.tools.sync_tool import register_sync_tools
from .essential.tools.create_deck_tool import register_create_deck_tools
from .essential.tools.find_notes_tool import register_find_notes_tool
from .essential.tools.notes_info_tool import register_notes_info_tool
from .essential.tools.list_decks_tool import register_list_decks_tool
from .essential.tools.add_note_tool import register_add_note_tool
from .essential.tools.model_names_tool import register_model_names_tool
from .essential.tools.model_field_names_tool import register_model_field_names_tool
from .essential.tools.model_styling_tool import register_model_styling_tool
from .essential.tools.update_model_styling_tool import register_update_model_styling_tool
from .essential.tools.delete_notes_tool import register_delete_notes_tool
from .essential.tools.update_note_fields_tool import register_update_note_fields_tool
from .essential.tools.get_due_cards_tool import register_get_due_cards_tool
from .essential.tools.create_model_tool import register_create_model_tool
from .essential.tools.present_card_tool import register_present_card_tool
from .essential.tools.rate_card_tool import register_rate_card_tool
from .essential.tools.store_media_file_tool import register_store_media_file_tool
from .essential.tools.get_media_files_names_tool import register_get_media_files_names_tool
from .essential.tools.delete_media_file_tool import register_delete_media_file_tool

# New deck management tools
from .essential.tools.rename_deck_tool import register_rename_deck_tool
from .essential.tools.delete_deck_tool import register_delete_deck_tool
from .essential.tools.change_deck_tool import register_change_deck_tool

# New tag management tools
from .essential.tools.add_tags_tool import register_add_tags_tool
from .essential.tools.remove_tags_tool import register_remove_tags_tool
from .essential.tools.get_tags_tool import register_get_tags_tool
from .essential.tools.clear_unused_tags_tool import register_clear_unused_tags_tool
from .essential.tools.update_note_tags_tool import register_update_note_tags_tool

# New card management tools
from .essential.tools.find_cards_tool import register_find_cards_tool
from .essential.tools.cards_info_tool import register_cards_info_tool
from .essential.tools.suspend_cards_tool import register_suspend_cards_tool
from .essential.tools.bury_cards_tool import register_bury_cards_tool
from .essential.tools.set_card_flag_tool import register_set_card_flag_tool

# New scheduling tools
from .essential.tools.set_due_date_tool import register_set_due_date_tool
from .essential.tools.forget_cards_tool import register_forget_cards_tool

# New utility tools
from .essential.tools.get_collection_stats_tool import register_get_collection_stats_tool
from .essential.tools.find_and_replace_tool import register_find_and_replace_tool

# Backup and import/export tools
from .essential.tools.backup_tool import register_backup_tool
from .essential.tools.restore_backup_tool import register_restore_backup_tool
from .essential.tools.import_export_tool import register_import_export_tool

# Import all GUI tools (this triggers handler registration at import time)
from .gui.tools.gui_current_card_tool import register_gui_current_card_tool
from .gui.tools.gui_add_cards_tool import register_gui_add_cards_tool
from .gui.tools.gui_browse_tool import register_gui_browse_tool
from .gui.tools.gui_deck_browser_tool import register_gui_deck_browser_tool
from .gui.tools.gui_show_answer_tool import register_gui_show_answer_tool
from .gui.tools.gui_show_question_tool import register_gui_show_question_tool
from .gui.tools.gui_edit_note_tool import register_gui_edit_note_tool
from .gui.tools.gui_select_card_tool import register_gui_select_card_tool
from .gui.tools.gui_undo_tool import register_gui_undo_tool


def register_all_tools(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register all MCP tools with the server.

    Args:
        mcp: FastMCP server instance
        call_main_thread: Async function to bridge calls to Anki's main thread
    """
    # Register essential tools
    register_sync_tools(mcp, call_main_thread)
    register_create_deck_tools(mcp, call_main_thread)
    register_find_notes_tool(mcp, call_main_thread)
    register_notes_info_tool(mcp, call_main_thread)
    register_list_decks_tool(mcp, call_main_thread)
    register_add_note_tool(mcp, call_main_thread)
    register_model_names_tool(mcp, call_main_thread)
    register_model_field_names_tool(mcp, call_main_thread)
    register_model_styling_tool(mcp, call_main_thread)
    register_update_model_styling_tool(mcp, call_main_thread)
    register_delete_notes_tool(mcp, call_main_thread)
    register_update_note_fields_tool(mcp, call_main_thread)
    register_get_due_cards_tool(mcp, call_main_thread)
    register_create_model_tool(mcp, call_main_thread)
    register_present_card_tool(mcp, call_main_thread)
    register_rate_card_tool(mcp, call_main_thread)
    register_store_media_file_tool(mcp, call_main_thread)
    register_get_media_files_names_tool(mcp, call_main_thread)
    register_delete_media_file_tool(mcp, call_main_thread)

    # Register new deck management tools
    register_rename_deck_tool(mcp, call_main_thread)
    register_delete_deck_tool(mcp, call_main_thread)
    register_change_deck_tool(mcp, call_main_thread)

    # Register new tag management tools
    register_add_tags_tool(mcp, call_main_thread)
    register_remove_tags_tool(mcp, call_main_thread)
    register_get_tags_tool(mcp, call_main_thread)
    register_clear_unused_tags_tool(mcp, call_main_thread)
    register_update_note_tags_tool(mcp, call_main_thread)

    # Register new card management tools
    register_find_cards_tool(mcp, call_main_thread)
    register_cards_info_tool(mcp, call_main_thread)
    register_suspend_cards_tool(mcp, call_main_thread)
    register_bury_cards_tool(mcp, call_main_thread)
    register_set_card_flag_tool(mcp, call_main_thread)

    # Register new scheduling tools
    register_set_due_date_tool(mcp, call_main_thread)
    register_forget_cards_tool(mcp, call_main_thread)

    # Register new utility tools
    register_get_collection_stats_tool(mcp, call_main_thread)
    register_find_and_replace_tool(mcp, call_main_thread)

    # Register backup and import/export tools
    register_backup_tool(mcp, call_main_thread)
    register_restore_backup_tool(mcp, call_main_thread)
    register_import_export_tool(mcp, call_main_thread)

    # Register GUI tools
    register_gui_current_card_tool(mcp, call_main_thread)
    register_gui_add_cards_tool(mcp, call_main_thread)
    register_gui_browse_tool(mcp, call_main_thread)
    register_gui_deck_browser_tool(mcp, call_main_thread)
    register_gui_show_answer_tool(mcp, call_main_thread)
    register_gui_show_question_tool(mcp, call_main_thread)
    register_gui_edit_note_tool(mcp, call_main_thread)
    register_gui_select_card_tool(mcp, call_main_thread)
    register_gui_undo_tool(mcp, call_main_thread)
