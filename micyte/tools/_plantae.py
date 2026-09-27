"""A taxon's photograph, resolved by a sandbox that holds no photographs.

TASK-2026-09-12-001 A4, the third receiver: *"a client's Brevat — a product profile naming
a taxon resolves that taxon's photo without the client holding the file"*.

The collection lives in FND's taxonomy sandbox and the pictures live beside it as ``art.``
documents. A seller pins the collection the same way it pins the taxonomy — one
declaration, read by the same resolver — and then a product that names a taxon has a
picture, with no copy of anything.

A collection is FILED, so its document is named by its slot (``1-1-2-3``), which is what
lets this recognise one cheaply: a pin whose name is an address is a filed document worth
opening, and a pin named ``txa`` or ``archetype_anchor`` is not. The metadata decides in
the end — ``{"collection": <title>}`` is written by `create_collection` and by nothing else.
"""

from __future__ import annotations

import re
from typing import Any

from ._shared.utilities import as_text

#: A filed document is named by its slot: digits and hyphens, nothing else.
_SLOT = re.compile(r"^\d+(?:-\d+)*$")


def _is_collection(document: Any) -> bool:
    metadata = getattr(document, "document_metadata", None) or {}
    return bool(as_text(metadata.get("collection")))


def collections_read_by(store: Any, *, tenant_id: str, sandbox: str,
                        msn: str = "") -> tuple[tuple[Any, str, str], ...]:
    """``(document, owner sandbox, owner msn)`` for every plantae collection this sandbox reads.

    Its own first, then the ones it DECLARES. A sandbox that pins nothing reads nothing,
    which is the same posture `_txa_options` takes: absence is not a licence to go looking
    through somebody else's books.
    """
    from micyte.core.instance_scope import use_instance

    from ._sources import declared_pins
    from ._viewscope import read_document

    out: list[tuple[Any, str, str]] = []
    sandbox, msn = as_text(sandbox), as_text(msn)
    with use_instance(msn) if msn else _nullcontext():
        own = list(store.read_documents_by_sandbox(
            tenant_id=tenant_id, sandbox=sandbox, msn_id=msn))
    out.extend((d, sandbox, msn) for d in own if _is_collection(d))
    for pin in declared_pins(store, tenant_id=tenant_id, sandbox=sandbox, msn=msn):
        name, owner = as_text(getattr(pin, "document_name", "")), as_text(getattr(pin, "sandbox", ""))
        if not (name and owner and _SLOT.match(name)):
            continue
        whose = as_text(getattr(pin, "node", ""))
        document_id = store.document_id_for(
            tenant_id=tenant_id, msn_id=whose, sandbox=owner, name=name)
        if not document_id:
            continue
        document = read_document(store, tenant_id=tenant_id, document_id=document_id)
        if document is not None and _is_collection(document):
            out.append((document, owner, whose))
    return tuple(out)


def taxon_photographs(store: Any, *, tenant_id: str, sandbox: str,
                      msn: str = "") -> dict[str, dict[str, str]]:
    """``{taxon: {slot, sandbox, msn, name}}`` from every collection this sandbox reads.

    First collection wins per taxon, the `build_reference_index` rule: two collections may
    honestly carry one taxon, and merging them would make the picture depend on read order.
    """
    from micyte.core import archetypes as arc
    from micyte.core.datum_ops import field_registry as _fr
    from micyte.core.datum_ops.plantae_profile import read_collection

    found: dict[str, dict[str, str]] = {}
    collections = collections_read_by(store, tenant_id=tenant_id, sandbox=sandbox, msn=msn)
    if not collections:
        return found
    library = store.read_documents_by_sandbox(tenant_id=tenant_id, sandbox=arc.ARCHETYPE_SANDBOX)
    registry = arc.registry_for(library)
    for document, owner, whose in collections:
        try:
            namespace = _fr.namespace_for_sandbox(owner, msn_id=whose)
        except KeyError:
            namespace = owner
        view = read_collection(document, registry=registry, namespace=namespace)
        for entry in view.entries:
            if entry.taxon and entry.slot:
                found.setdefault(entry.taxon, {
                    "slot": entry.slot, "sandbox": owner, "msn": whose, "name": entry.name})
    return found


class _nullcontext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> None:
        return None


__all__ = ["collections_read_by", "taxon_photographs"]
