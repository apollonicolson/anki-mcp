"""Image occlusion tools."""
import os
from .base import T, ToolError, col


@T("add-image-occlusion-note", "Create image occlusion cards", write=True)
def add_image_occlusion_note(image_path: str, occlusions: list[dict], deck_name: str, tags: list[str] = None):
    """Create image occlusion cards from an image.

    occlusions: List of dicts with {left, top, width, height} for each mask
    """
    if not os.path.exists(image_path):
        raise ToolError(f"Image not found: {image_path}")

    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    import base64
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    from anki.image_occlusion import AddImageOcclusionNoteRequest

    request = AddImageOcclusionNoteRequest(
        image_data=image_data,
        occlusions=str(occlusions),
        deck_id=deck["id"],
        tags=tags or [],
    )

    result = col().add_image_occlusion_note(request)
    return {"noteId": result.note_id, "deckName": deck_name}


@T("get-image-occlusion-note", "Get occlusion config for existing note")
def get_image_occlusion_note(note_id: int):
    """Get image occlusion configuration for an existing note."""
    result = col().get_image_occlusion_note(note_id)
    return {
        "noteId": note_id,
        "imageData": result.image_data[:100] + "..." if result.image_data else None,
        "occlusions": result.occlusions,
    }
