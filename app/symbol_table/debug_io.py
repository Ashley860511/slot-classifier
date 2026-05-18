"""Best-effort debug output helpers for symbol table generation."""

from pathlib import Path


def safe_save_debug_image(img, path: Path, **kwargs) -> bool:
    """Write a debug image without allowing locked files to break extraction."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, **kwargs)
        return True
    except Exception as exc:
        print(f"    [debug] skip writing {path.name}: {exc}")
        return False


def safe_write_debug_text(path: Path, text: str) -> bool:
    """Write debug HTML/text without allowing open browser files to break extraction."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return True
    except Exception as exc:
        print(f"    [debug] skip writing {path.name}: {exc}")
        return False
