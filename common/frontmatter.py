from __future__ import annotations

from collections import OrderedDict


def parse_frontmatter_block(text: str) -> tuple[OrderedDict[str, str], int]:
    if not text.startswith("---"):
        return OrderedDict(), -1
    end = text.find("\n---", 3)
    if end == -1:
        return OrderedDict(), -1

    raw = text[3:end].strip()
    result: OrderedDict[str, str] = OrderedDict()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result, end + 4


def get_frontmatter_value(text: str, key: str, default: str = "") -> str:
    data, _ = parse_frontmatter_block(text)
    return data.get(key, default)


def update_frontmatter_values(text: str, updates: dict[str, str]) -> str:
    data, end = parse_frontmatter_block(text)
    if end == -1:
        return text

    for k, v in updates.items():
        data[k] = str(v)

    frontmatter = "\n".join(f"{k}: {v}" for k, v in data.items())
    return f"---\n{frontmatter}\n---" + text[end:]
