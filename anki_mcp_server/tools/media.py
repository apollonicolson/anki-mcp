"""Media file management tools."""
import os
from .base import T, ToolError, col


@T("store-media-file", "Store a media file")
def store_media_file(filename: str, data: str = None, path: str = None, url: str = None):
    import base64
    import urllib.request

    if data:
        content = base64.b64decode(data)
    elif path:
        with open(path, "rb") as f:
            content = f.read()
    elif url:
        content = urllib.request.urlopen(url).read()
    else:
        raise ToolError("Must provide data, path, or url")

    stored = col().media.write_data(filename, content)
    return {"filename": stored}


@T("retrieve-media-file", "Get media file as base64")
def retrieve_media_file(filename: str):
    import base64
    path = os.path.join(col().media.dir(), filename)
    if not os.path.exists(path):
        raise ToolError(f"File not found: {filename}")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return {"filename": filename, "data": data}


@T("list-media-files", "List media files matching pattern")
def list_media_files(pattern: str = "*", limit: int = 100, offset: int = 0):
    """List media files with optional filtering and pagination."""
    import fnmatch
    all_files = os.listdir(col().media.dir())
    matched = [f for f in all_files if fnmatch.fnmatch(f, pattern)]
    total = len(matched)
    files = matched[offset:offset + limit]
    return {"files": files, "count": len(files), "total": total, "hasMore": offset + limit < total}


T("get-media-dir-path", "Get path to media folder", lambda: col().media.dir())


@T("delete-media-file", "Delete a media file")
def delete_media_file(filename: str):
    path = os.path.join(col().media.dir(), filename)
    if os.path.exists(path):
        os.remove(path)
        return {"deleted": filename}
    raise ToolError(f"File not found: {filename}")


@T("check-media", "Check for missing or unused media files")
def check_media():
    result = col().media.check()
    return {
        "missing": list(result.missing),
        "unused": list(result.unused),
        "missingCount": len(result.missing),
        "unusedCount": len(result.unused),
    }
