"""GUI interaction tools."""
import os
from .base import T, ToolError, col


@T("gui-browse", "Open card browser with search", category="gui")
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


@T("gui-add-cards", "Open Add Cards dialog", category="gui", require_col=False)
def gui_add_cards(deck_name: str = None, model_name: str = None, fields: dict = None):
    from aqt import mw
    mw.onAddCard()
    add = mw.app.activeWindow()

    if deck_name:
        deck = col().decks.by_name(deck_name)
        if deck:
            add.deckChooser.deck.setText(deck_name)

    return {"opened": True}


@T("gui-current-card", "Get info about card in reviewer", category="gui")
def gui_current_card():
    from aqt import mw
    if not mw.reviewer or not mw.reviewer.card:
        return {"inReview": False}
    c = mw.reviewer.card
    return {
        "inReview": True, "cardId": c.id, "noteId": c.nid, "deckId": c.did,
        "question": c.question(), "answer": c.answer(),
    }


@T("gui-show-answer", "Show answer in reviewer", category="gui")
def gui_show_answer():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._showAnswer()
        return {"shown": True}
    return {"shown": False, "error": "Not in review"}


@T("gui-show-question", "Show question in reviewer", category="gui")
def gui_show_question():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._showQuestion()
        return {"shown": True}
    return {"shown": False, "error": "Not in review"}


@T("gui-deck-browser", "Open deck browser", category="gui")
def gui_deck_browser():
    from aqt import mw
    mw.moveToState("deckBrowser")
    return {"opened": True}


@T("gui-undo", "Undo last action", category="gui")
def gui_undo():
    from aqt import mw
    if col().undo_status().undo:
        mw.undo()
        return {"undone": True}
    return {"undone": False, "error": "Nothing to undo"}


@T("gui-edit-note", "Open note editor", category="gui")
def gui_edit_note(note_id: int):
    from aqt import mw
    mw.onBrowse()
    browser = mw.app.activeWindow()
    browser.form.searchEdit.lineEdit().setText(f"nid:{note_id}")
    browser.onSearchActivated()
    return {"opened": True, "noteId": note_id}


@T("gui-select-card", "Select card in browser", category="gui")
def gui_select_card(card_id: int):
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if isinstance(browser, Browser):
        browser.selectCards([card_id])
        return {"selected": card_id}
    return {"selected": False, "error": "Browser not open"}


@T("gui-selected-notes", "Get selected notes in browser", category="gui")
def gui_selected_notes():
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if isinstance(browser, Browser):
        return {"notes": list(set(c.nid for c in browser.selectedCards()))}
    return {"notes": [], "error": "Browser not open"}


@T("gui-start-card-timer", "Start timer for current card", category="gui")
def gui_start_card_timer():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer.card.startTimer()
        return {"started": True}
    return {"started": False, "error": "Not in review"}


@T("gui-answer-card", "Answer current card in reviewer", category="gui", write=True)
def gui_answer_card(ease: int):
    from aqt import mw
    if not 1 <= ease <= 4:
        raise ToolError("Ease must be 1-4")
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._answerCard(ease)
        return {"answered": True, "ease": ease}
    return {"answered": False, "error": "Not in review"}


@T("gui-deck-overview", "Open deck overview", category="gui")
def gui_deck_overview(deck_name: str):
    from aqt import mw
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.select(deck["id"])
    mw.moveToState("overview")
    return {"opened": True, "deckName": deck_name}


@T("gui-deck-review", "Start reviewing a deck", category="gui")
def gui_deck_review(deck_name: str):
    from aqt import mw
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.select(deck["id"])
    mw.moveToState("review")
    return {"started": True, "deckName": deck_name}


@T("gui-import-file", "Open import dialog for a file", category="gui")
def gui_import_file(path: str):
    from aqt import mw
    if not os.path.exists(path):
        raise ToolError(f"File not found: {path}")
    mw.handleImport(path)
    return {"importing": path}


@T("gui-exit-anki", "Close Anki", category="gui", require_col=False)
def gui_exit_anki():
    from aqt import mw
    mw.close()
    return {"closing": True}


@T("gui-check-database", "Check database integrity", category="gui")
def gui_check_database():
    from aqt import mw
    result = mw.col.fix_integrity()
    return {"result": result}


@T("gui-play-audio", "Play audio for current card", category="gui")
def gui_play_audio(side: str = "question"):
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer.playAudio("answer" if side == "answer" else "question")
        return {"playing": True, "side": side}
    return {"playing": False, "error": "Not in review"}
