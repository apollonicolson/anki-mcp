"""Shared text normalisation.

anki_cli and analysis each carried a private copy of this: byte-identical strip
bodies and equal symbol tables, differing only in the names. Duplicated
normalisation is how two callers quietly start disagreeing about whether two
notes are duplicates.
"""
from html import unescape
import re
from typing import Any

TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
BR_RE = re.compile(r"<br\s*/?>", re.I)
SPACE_RE = re.compile(r"\s+")
NON_TEXT_RE = re.compile(r"[^a-z0-9_+\-*/=<>^()., :;?\[\]{}|]+")

SYMBOLS = {
    "−": "-", "–": "-", "—": "-",
    "×": "x", "∙": "x", "⋅": "x", "÷": "/",
    "²": "^2", "³": "^3",
    "≤": "<=", "≥": ">=", "√": "sqrt",
}


def strip_html(value: Any) -> str:
    """Visible text of a field: markup removed, images marked, whitespace collapsed."""
    text = "" if value is None else str(value)
    text = unescape(text)
    text = IMG_RE.sub(" [image] ", text)
    text = BR_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    return SPACE_RE.sub(" ", text).strip()


def norm(value: Any) -> str:
    """Comparison form: lowercased, symbols folded, punctuation dropped."""
    text = strip_html(value).lower()
    for src, dst in SYMBOLS.items():
        text = text.replace(src, dst)
    text = NON_TEXT_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()
