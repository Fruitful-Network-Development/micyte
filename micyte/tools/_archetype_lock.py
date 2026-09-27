"""The archetype hashes this build's packages were written against (``_archetypes.lock.json``).

Written by ``scripts/lock_archetypes.py`` from the library the build is developed against;
read here, once, and handed to :func:`micyte.tools._packages._package` so every document
requirement carries the hash of the archetype it names. See the lock's own docstring for
why a pin rather than a hand-kept version: the archetype IS a document, and a document
already has a hash.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCK_PATH = Path(__file__).with_name("_archetypes.lock.json")
SCHEMA = "micyte.archetypes.lock.v1"


@lru_cache(maxsize=1)
def lock() -> dict[str, str]:
    """``{archetype name: hash}``, or ``{}`` when the build ships no lock."""
    if not LOCK_PATH.exists():
        return {}
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError(f"{LOCK_PATH.name} is not a {SCHEMA} file")
    entries = payload.get("archetypes") or {}
    return {str(k): str(v) for k, v in entries.items()}


def archetype_hash(name: str) -> str:
    """The pinned hash for ``name``, or ``""`` when the lock does not name it."""
    return lock().get(str(name or ""), "")


__all__ = ["LOCK_PATH", "SCHEMA", "archetype_hash", "lock"]
