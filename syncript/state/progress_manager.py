"""
Progress file management (checkpoint for current sync run)
"""
import json
from ..config import get_progress_file


_PROGRESS_KEYS = ("pushed", "pulled", "deleted_r", "deleted_l")


def new_progress() -> dict:
    """Create an empty progress structure with all required keys."""
    return {key: [] for key in _PROGRESS_KEYS}


def normalize_progress(prog: dict | None) -> dict:
    """Normalize arbitrary progress payloads to the expected shape."""
    if not isinstance(prog, dict):
        return new_progress()
    normalized = new_progress()
    for key in _PROGRESS_KEYS:
        value = prog.get(key, [])
        normalized[key] = value if isinstance(value, list) else []
    return normalized


def load_progress() -> dict:
    """
    Format: {"pushed": [...], "pulled": [...], "deleted_r": [...], "deleted_l": [...]}
    """
    if get_progress_file().exists():
        try:
            return normalize_progress(json.loads(get_progress_file().read_text("utf-8")))
        except Exception:
            pass
    return new_progress()


def save_progress(prog: dict):
    """Save progress to checkpoint file"""
    get_progress_file().write_text(json.dumps(normalize_progress(prog), indent=2), "utf-8")


def clear_progress():
    """Remove progress file after successful sync"""
    if get_progress_file().exists():
        get_progress_file().unlink()
