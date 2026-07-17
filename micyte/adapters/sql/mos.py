"""Single construction entry point (facade) for the MOS datum store.

Every consumer that needs a :class:`SqliteSystemDatumStoreAdapter` for an
authority database should call :func:`open_mos_store` instead of constructing the
adapter directly, so the MOS submodule has exactly one place that owns adapter
construction and its write posture.

Write posture is canonical-only (``allow_legacy_writes=False``): live data is
fully canonical and the adapter refuses to re-persist any non-canonical catalog
id. ``cache`` is opt-in — the default returns a fresh adapter per call (matching
the historical direct-construction behaviour at the scattered call sites); the
shared read path (``instances/_shared/datum_store_accessor``) opts in so all its
callers share one mtime-guarded instance per authority db.
"""

from __future__ import annotations

from pathlib import Path

from .datum_store import SqliteSystemDatumStoreAdapter

# Cache is keyed by (resolved path, write posture) so a caller can never receive
# an instance created under a different posture than it asked for.
_MOS_STORE_BY_AUTHORITY_DB: dict[tuple[str, bool], SqliteSystemDatumStoreAdapter] = {}


def open_mos_store(
    authority_db_file: str | Path | None,
    *,
    allow_legacy_writes: bool = False,
    cache: bool = False,
) -> SqliteSystemDatumStoreAdapter | None:
    """Return a MOS datum-store adapter for ``authority_db_file``.

    Returns ``None`` when ``authority_db_file`` is ``None`` (so Optional-path
    callers can pass through). When ``cache`` is true, adapters are memoised per
    resolved path + write posture so callers within a process share one instance
    and its catalog cache; when false (the default) a fresh adapter is returned.
    """
    if authority_db_file is None:
        return None
    root = Path(authority_db_file)
    if not cache:
        return SqliteSystemDatumStoreAdapter(root, allow_legacy_writes=allow_legacy_writes)
    cache_key = (str(root.resolve()), bool(allow_legacy_writes))
    cached = _MOS_STORE_BY_AUTHORITY_DB.get(cache_key)
    if cached is not None:
        return cached
    store = SqliteSystemDatumStoreAdapter(root, allow_legacy_writes=allow_legacy_writes)
    _MOS_STORE_BY_AUTHORITY_DB[cache_key] = store
    return store
