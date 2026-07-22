"""Deck management tools."""
from .base import T, ToolError, col


def _sparse(d: dict) -> dict:
    """Remove keys with falsy values (0, None, [], '', {}) from dict, recursively."""
    return {k: (_sparse(v) if isinstance(v, dict) else
                [_sparse(i) if isinstance(i, dict) else i for i in v] if isinstance(v, list) else v)
            for k, v in d.items() if v or v is False}


@T("list-decks", "List decks with optional filtering and statistics")
def list_decks(
    include_stats: bool = False,
    pattern: str = None,
    depth: int = -1,
    limit: int = 100,
    offset: int = 0,
    sparse: bool = True,
):
    """List decks with optional filtering and pagination.

    Args:
        depth: Max nesting level (-1=unlimited, 0=root only, 1=root+children, etc.)
        sparse: Omit zero/empty values from output (default True)
    """
    import fnmatch

    if include_stats:
        tree = col().sched.deck_due_tree()

        def process_node(node, current_depth=0):
            if depth >= 0 and current_depth > depth:
                return None
            if pattern and not fnmatch.fnmatch(node.name.lower(), pattern.lower()):
                matching_children = [c for c in (process_node(child, current_depth + 1) for child in node.children) if c]
                if not matching_children:
                    return None
            children = []
            if depth < 0 or current_depth < depth:
                children = [c for c in (process_node(child, current_depth + 1) for child in node.children) if c]
            result = {
                "id": node.deck_id,
                "name": node.name,
                "new": node.new_count,
                "learn": node.learn_count,
                "review": node.review_count,
                "children": children,
            }
            return _sparse(result) if sparse else result

        all_decks = [d for d in (process_node(n) for n in tree.children) if d]
        total = len(all_decks)
        decks = all_decks[offset:offset + limit]
        meta = {"decks": decks, "total": total}
        if offset + limit < total:
            meta["hasMore"] = True
        return _sparse(meta) if sparse else meta

    all_decks = col().decks.all()
    filtered_decks = []
    for d in all_decks:
        name = d["name"]
        nest_level = name.count("::")
        if depth >= 0 and nest_level > depth:
            continue
        if pattern and not fnmatch.fnmatch(name.lower(), pattern.lower()):
            continue
        filtered_decks.append({"id": d["id"], "name": name})

    total = len(filtered_decks)
    decks = filtered_decks[offset:offset + limit]
    meta = {"decks": decks, "total": total}
    if offset + limit < total:
        meta["hasMore"] = True
    return meta


@T("create-deck", "Create a new deck. Supports parent::child structure.")
def create_deck(deck_name: str):
    did = col().decks.id(deck_name)
    return {"deckId": did, "deckName": deck_name, "created": True}


@T("rename-deck", "Rename a deck", write=True)
def rename_deck(old_name: str, new_name: str):
    deck = col().decks.by_name(old_name)
    if not deck:
        raise ToolError(f"Deck not found: {old_name}", hint="Use list-decks to see available decks")
    deck["name"] = new_name
    col().decks.save(deck)
    return {"oldName": old_name, "newName": new_name}


@T("delete-deck", "Delete a deck", write=True)
def delete_deck(deck_name: str, cards_too: bool = False):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.remove([deck["id"]])
    return {"deleted": deck_name, "cardsDeleted": cards_too}


def change_deck(cards: list[int], deck_name: str):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().set_deck(cards, deck["id"])
    return {"moved": len(cards), "toDeck": deck_name}


def get_deck_config(deck_name: str):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    conf = col().decks.config_dict_for_deck_id(deck["id"])
    return {"deckName": deck_name, "config": conf}


def get_deck_stats(deck_name: str):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    return {"deckName": deck_name, "deckId": deck["id"]}


def save_deck_config(config: dict):
    col().decks.save(config)
    return {"saved": True, "configId": config.get("id")}


def set_deck_config_id(deck_name: str, config_id: int):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    deck["conf"] = config_id
    col().decks.save(deck)
    return {"deckName": deck_name, "configId": config_id}


def clone_deck_config_id(config_id: int, clone_name: str):
    conf = col().decks.get_config(config_id)
    if not conf:
        raise ToolError(f"Config not found: {config_id}")
    new_conf = col().decks.add_config(clone_name)
    return {"originalId": config_id, "cloneId": new_conf["id"], "cloneName": clone_name}


def delete_deck_config(config_id: int):
    col().decks.remove_config(config_id)
    return {"removed": config_id}


@T("get-decks-for-cards", "Get decks containing specific cards")
def get_decks_for_cards(cards: list[int]):
    deck_map = {}
    for cid in cards:
        c = col().get_card(cid)
        name = col().decks.name(c.did)
        if name not in deck_map:
            deck_map[name] = []
        deck_map[name].append(cid)
    return deck_map


def get_deck_due_tree(sparse: bool = True):
    """Get full deck tree with due counts.

    Args:
        sparse: Omit zero/empty values from output (default True)
    """
    tree = col().sched.deck_due_tree()

    def process_node(node):
        result = {
            "id": node.deck_id,
            "name": node.name,
            "new": node.new_count,
            "learn": node.learn_count,
            "review": node.review_count,
            "children": [process_node(child) for child in node.children],
        }
        return _sparse(result) if sparse else result

    return {"tree": [process_node(n) for n in tree.children]}
