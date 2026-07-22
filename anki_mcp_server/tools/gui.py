"""GUI interaction tools."""
import os
from .base import T, ToolError, col


def gui_browse(query: str = ""):
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if not isinstance(browser, Browser):
        mw.onBrowse()
        browser = mw.app.activeWindow()
    if query:
        browser.form.searchEdit.lineEdit().setText(query)
        browser.onSearchActivated()
    return {"opened": True, "query": query}


def gui_add_cards(deck_name: str = None, model_name: str = None, fields: dict = None):
    from aqt import mw
    mw.onAddCard()
    add = mw.app.activeWindow()

    if deck_name:
        deck = col().decks.by_name(deck_name)
        if deck:
            add.deckChooser.deck.setText(deck_name)

    return {"opened": True}


def gui_current_card():
    from aqt import mw
    if not mw.reviewer or not mw.reviewer.card:
        return {"inReview": False}
    c = mw.reviewer.card
    return {
        "inReview": True, "cardId": c.id, "noteId": c.nid, "deckId": c.did,
        "question": c.question(), "answer": c.answer(),
    }


def gui_show_answer():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._showAnswer()
        return {"shown": True}
    return {"shown": False, "error": "Not in review"}


def gui_show_question():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._showQuestion()
        return {"shown": True}
    return {"shown": False, "error": "Not in review"}


def gui_deck_browser():
    from aqt import mw
    mw.moveToState("deckBrowser")
    return {"opened": True}


def gui_undo():
    from aqt import mw
    if col().undo_status().undo:
        mw.undo()
        return {"undone": True}
    return {"undone": False, "error": "Nothing to undo"}


def gui_edit_note(note_id: int):
    from aqt import mw
    mw.onBrowse()
    browser = mw.app.activeWindow()
    browser.form.searchEdit.lineEdit().setText(f"nid:{note_id}")
    browser.onSearchActivated()
    return {"opened": True, "noteId": note_id}


def gui_select_card(card_id: int):
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if isinstance(browser, Browser):
        browser.selectCards([card_id])
        return {"selected": card_id}
    return {"selected": False, "error": "Browser not open"}


def gui_selected_notes():
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if isinstance(browser, Browser):
        return {"notes": list(set(c.nid for c in browser.selectedCards()))}
    return {"notes": [], "error": "Browser not open"}


def gui_start_card_timer():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer.card.startTimer()
        return {"started": True}
    return {"started": False, "error": "Not in review"}


def gui_answer_card(ease: int):
    from aqt import mw
    if not 1 <= ease <= 4:
        raise ToolError("Ease must be 1-4")
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._answerCard(ease)
        return {"answered": True, "ease": ease}
    return {"answered": False, "error": "Not in review"}


def gui_deck_overview(deck_name: str):
    from aqt import mw
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.select(deck["id"])
    mw.moveToState("overview")
    return {"opened": True, "deckName": deck_name}


def gui_deck_review(deck_name: str):
    from aqt import mw
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.select(deck["id"])
    mw.moveToState("review")
    return {"started": True, "deckName": deck_name}


def gui_import_file(path: str):
    from aqt import mw
    if not os.path.exists(path):
        raise ToolError(f"File not found: {path}")
    mw.handleImport(path)
    return {"importing": path}


def gui_exit_anki():
    from aqt import mw
    mw.close()
    return {"closing": True}


def gui_check_database():
    from aqt import mw
    result = mw.col.fix_integrity()
    return {"result": result}


def gui_play_audio(side: str = "question"):
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer.playAudio("answer" if side == "answer" else "question")
        return {"playing": True, "side": side}
    return {"playing": False, "error": "Not in review"}


# One tool, one enum. These are UI actions, not data operations - they cannot be
# dry-run or reverted, so they keep an explicit verb and stay out of the journal.
GUI_ACTIONS = {
    "browse": gui_browse,
    "add-cards": gui_add_cards,
    "current-card": gui_current_card,
    "show-answer": gui_show_answer,
    "show-question": gui_show_question,
    "deck-browser": gui_deck_browser,
    "undo": gui_undo,
    "edit-note": gui_edit_note,
    "select-card": gui_select_card,
    "selected-notes": gui_selected_notes,
    "start-card-timer": gui_start_card_timer,
    "answer-card": gui_answer_card,
    "deck-overview": gui_deck_overview,
    "deck-review": gui_deck_review,
    "import-file": gui_import_file,
    "exit-anki": gui_exit_anki,
    "check-database": gui_check_database,
    "play-audio": gui_play_audio,
}


@T("gui", "Drive Anki's user interface: browse, review, dialogs, undo",
   category="gui", require_col=False)
def gui(do: str, args: dict = None):
    """Dispatch a UI action. `do` names the action, `args` are its parameters.

    Nested args rather than **kwargs: the MCP schema is generated from this
    signature, and a bare **kwargs produces no usable parameter description.
    """
    action = GUI_ACTIONS.get(do)
    if action is None:
        raise ToolError(f"Unknown gui action: {do}",
                        hint=f"one of {sorted(GUI_ACTIONS)}")
    return action(**(args or {}))
