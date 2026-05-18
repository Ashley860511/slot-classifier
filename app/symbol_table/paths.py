"""Filesystem collection helpers for symbol table generation."""

from pathlib import Path


def collect_help_images(video_dir: Path, max_pages: int = 10) -> list[Path]:
    """
    Return up to max_pages Help screenshots, evenly sampled across the sequence.

    This is used for HTML thumbnail strips only. Paytable scanning should use
    collect_paytable_scan_images(), which includes low_score/Help as well.
    """
    d = video_dir / "Help"
    if not d.exists():
        return []
    all_files = sorted(d.glob("*.jpg"))
    n = len(all_files)
    if n <= max_pages:
        return all_files
    step = (n - 1) / (max_pages - 1)
    indices = sorted(set(round(i * step) for i in range(max_pages)))
    return [all_files[i] for i in indices]


def collect_all_help_images(video_dir: Path) -> list[Path]:
    """Return all final Help screenshots sorted by filename."""
    d = video_dir / "Help"
    if not d.exists():
        return []
    return sorted(d.glob("*.jpg"))


def collect_paytable_scan_images(video_dir: Path) -> list[Path]:
    """
    Return Help screenshots for local paytable detection.

    Prefer final Help because main.py now keeps it as a rules corpus. Also scan
    low_score/Help so symbol extraction is not blocked by final sampling.
    """
    seen: set[str] = set()
    images: list[Path] = []
    for d in [video_dir / "Help", video_dir / "low_score" / "Help"]:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.jpg")):
            key = p.name
            if key in seen:
                continue
            seen.add(key)
            images.append(p)
    return images


def collect_basegame_images(video_dir: Path, max_frames: int = 12) -> list[Path]:
    """Return Basegame frames, preferring final high-score frames then low_score."""
    frames = sorted((video_dir / "Basegame").glob("*.jpg"))[:max_frames]
    if len(frames) < 4:
        frames += sorted((video_dir / "low_score" / "Basegame").glob("*.jpg"))[:max_frames]
    return frames[:max_frames]
