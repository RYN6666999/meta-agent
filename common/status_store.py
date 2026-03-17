from __future__ import annotations

from collections.abc import Callable
from typing import Any

from common.config import STATUS_FILE
from common.jsonio import load_json, save_json


StatusMutator = Callable[[dict[str, Any]], None]


def load_status() -> dict[str, Any]:
    return load_json(STATUS_FILE, {})


def save_status(data: dict[str, Any]) -> None:
    save_json(STATUS_FILE, data)


def update_status(mutator: StatusMutator) -> dict[str, Any]:
    data = load_status()
    if not isinstance(data, dict):
        data = {}
    mutator(data)
    save_status(data)
    return data
