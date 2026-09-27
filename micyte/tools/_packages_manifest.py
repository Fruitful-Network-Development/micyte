"""The packages a publisher offers, as a hashed, versioned payload that crosses the network.

The marketplace is a port (``micyte.ports.tool_package``): ``LocalPackageSource`` is what
the build in front of you contains, and the ``official`` source is "packages fetched from
micyte.com, with everything downstream unchanged". This module is that payload and its two
halves — what a publisher WRITES and what an instance READS — kept in one file so the two
cannot describe the declaration differently.

An entry is the package's whole declaration (every field the dataclass carries) beside the
digest of that declaration — the same digest ``scripts/lock_packages.py`` pins, so an
instance can check that what arrived is what was published and a publisher's lock says
what an instance will compute. The reader rebuilds the port's frozen dataclasses by
introspection rather than by a hand-written field list: a field added to the port later
rides through without a second place to forget, and the dataclasses' own ``__post_init__``
validation runs on what arrived. An entry that does not hash to its digest is refused, not
repaired. What the reader returns is marked ``SOURCE_OFFICIAL``: the source is a fact about
where the reader got it, not part of the declaration.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
import typing
from typing import Any

from micyte.ports.tool_package import (
    SOURCE_OFFICIAL,
    ToolPackage,
    ToolPackageError,
    ToolPackageSource,
)

MANIFEST_SCHEMA = "micyte.packages.manifest.v1"

#: What is NOT part of a package's declaration: its version (the thing the digest
#: decides), and the words a human reads. One definition; the lock script uses this one.
EXCLUDED_FROM_DIGEST = ("version", "label", "summary", "icon")


def declaration_digest(package: ToolPackage) -> str:
    """``sha256:…`` over the package's declaration — every field but the excluded ones,
    canonically serialized. The lock pins this; the manifest carries it."""
    payload = dataclasses.asdict(package)
    for key in EXCLUDED_FROM_DIGEST:
        payload.pop(key, None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def package_to_dict(package: ToolPackage) -> dict[str, Any]:
    """The whole declaration, beside its digest."""
    return {**dataclasses.asdict(package), "digest": declaration_digest(package)}


def manifest_of(
    packages: Any, *, publisher: str, build: str, micyte_version: str,
) -> dict[str, Any]:
    """What a publisher serves: its catalogue, sorted by id, under the schema."""
    entries = sorted((package_to_dict(p) for p in packages), key=lambda e: e["package_id"])
    return {
        "schema": MANIFEST_SCHEMA,
        "publisher": str(publisher or ""),
        "build": str(build or ""),
        "micyte_version": str(micyte_version or ""),
        "packages": entries,
    }


def _construct(annotation: Any, value: Any) -> Any:
    """``value`` as the type ``annotation`` names — a dataclass, a tuple of them, an
    optional one — or as it is, for a plain value."""
    origin = typing.get_origin(annotation)
    if origin in (types.UnionType, typing.Union):
        members = [a for a in typing.get_args(annotation) if a is not type(None)]
        if value is None:
            return None
        return _construct(members[0], value) if len(members) == 1 else value
    if origin is tuple:
        args = typing.get_args(annotation)
        inner = args[0] if args else Any
        return tuple(_construct(inner, item) for item in (value or ()))
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        if not isinstance(value, dict):
            raise ToolPackageError(
                f"{annotation.__name__} arrived as {type(value).__name__}, not an object")
        return _build(annotation, value)
    return value


def _build(cls: type, data: dict[str, Any]) -> Any:
    hints = typing.get_type_hints(cls)
    known = {f.name for f in dataclasses.fields(cls) if f.init}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ToolPackageError(
            f"{cls.__name__} arrived with fields this build does not know: {', '.join(unknown)}")
    kwargs = {name: _construct(hints[name], data[name]) for name in data if name in known}
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise ToolPackageError(f"{cls.__name__} could not be rebuilt: {exc}") from exc


def package_from_dict(entry: dict[str, Any]) -> ToolPackage:
    """One entry rebuilt, its digest checked, marked official."""
    if not isinstance(entry, dict):
        raise ToolPackageError(f"a package entry arrived as {type(entry).__name__}, not an object")
    carried = str(entry.get("digest") or "")
    declaration = {k: v for k, v in entry.items() if k != "digest"}
    package = _build(ToolPackage, declaration)
    computed = declaration_digest(package)
    if not carried or carried != computed:
        raise ToolPackageError(
            f"package {package.package_id!r} arrived with a declaration that does not hash to "
            f"its digest ({carried[:19] or 'none'}… carried, {computed[:19]}… computed)")
    return dataclasses.replace(package, source=SOURCE_OFFICIAL)


def packages_from_manifest(payload: Any) -> tuple[ToolPackage, ...]:
    """Every package a manifest carries, or a refusal naming the first entry that is not
    what it claims. The schema is checked first: a payload from some other door is not a
    catalogue with zero packages."""
    if not isinstance(payload, dict) or payload.get("schema") != MANIFEST_SCHEMA:
        raise ToolPackageError(
            f"not a {MANIFEST_SCHEMA} manifest (schema "
            f"{(payload or {}).get('schema') if isinstance(payload, dict) else type(payload).__name__!r})")
    entries = payload.get("packages")
    if not isinstance(entries, list):
        raise ToolPackageError("the manifest's packages are not a list")
    packages = tuple(package_from_dict(entry) for entry in entries)
    ids = [p.package_id for p in packages]
    if len(set(ids)) != len(ids):
        raise ToolPackageError("the manifest names a package twice")
    return packages


class OfficialPackageSource:
    """The ``official`` source the port names: a manifest a publisher served, read."""

    source_id = SOURCE_OFFICIAL

    def __init__(self, payload: dict[str, Any]) -> None:
        self._packages = packages_from_manifest(payload)
        self.publisher = str(payload.get("publisher") or "")
        self.build = str(payload.get("build") or "")
        self.micyte_version = str(payload.get("micyte_version") or "")

    def available(self) -> tuple[ToolPackage, ...]:
        return self._packages


# The Protocol is runtime_checkable, so this is a real check rather than a comment.
assert isinstance(OfficialPackageSource({"schema": MANIFEST_SCHEMA, "packages": []}), ToolPackageSource)

__all__ = [
    "EXCLUDED_FROM_DIGEST",
    "MANIFEST_SCHEMA",
    "OfficialPackageSource",
    "declaration_digest",
    "manifest_of",
    "package_from_dict",
    "package_to_dict",
    "packages_from_manifest",
]
