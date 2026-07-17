from __future__ import annotations

import re

_DOMAIN_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_plain_domain(value: object) -> bool:
    token = _as_text(value).lower()
    if not token:
        return False
    if len(token) > 253 or "/" in token or "\\" in token or ".." in token:
        return False
    if token.startswith(".") or token.endswith("."):
        return False
    labels = token.split(".")
    if len(labels) < 2:
        return False
    return all(bool(_DOMAIN_LABEL_PATTERN.match(label)) for label in labels)


def normalize_optional_plain_domain(value: object, *, field_name: str) -> str:
    token = _as_text(value).lower()
    if not token:
        return ""
    if not is_plain_domain(token):
        raise ValueError(f"{field_name} must be a plain domain-like value")
    return token


def require_plain_domain(value: object, *, field_name: str) -> str:
    token = normalize_optional_plain_domain(value, field_name=field_name)
    if not token:
        raise ValueError(f"{field_name} must be a plain domain-like value")
    return token


__all__ = [
    "is_plain_domain",
    "normalize_optional_plain_domain",
    "require_plain_domain",
]
