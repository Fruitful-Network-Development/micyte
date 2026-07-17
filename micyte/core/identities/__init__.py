"""Identity normalization helpers shared across ports and modules."""

from .domains import is_plain_domain, normalize_optional_plain_domain, require_plain_domain

__all__ = [
    "is_plain_domain",
    "normalize_optional_plain_domain",
    "require_plain_domain",
]
