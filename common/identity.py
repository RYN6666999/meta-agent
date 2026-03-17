from __future__ import annotations


def normalize_id(raw: str, default: str = "default", max_len: int = 64) -> str:
    safe = "".join(ch for ch in (raw or "") if ch.isalnum() or ch in "_-").strip("_-")
    return safe[:max_len] if safe else default
