from __future__ import annotations

from typing import Any


def as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def as_dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


__all__ = [
    "as_dict",
    "as_dict_list",
    "as_list",
    "as_text",
]
