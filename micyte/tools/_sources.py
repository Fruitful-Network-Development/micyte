"""The document a sandbox READS: its own, or the one it DECLARES as a source.

TASK-2026-09-12-001. Operator, 2026-09-12: *"Should for most be a use of txa"* — a product
profile is meant to carry the taxon that organizes it, and until now only a sandbox holding
its own ``txa`` could cite one. The farm instance's ``brevat`` sandbox holds no taxonomy and
never will: there is exactly one taxonomy in this store, FND's, and copying 4,118 rows into
every seller's books would be two denotations of one tree.

The mechanism for reading somebody else's document already exists and is already used —
`resolve_sources`, the manifest pin, and the local domain's own ``sources`` branch. TFF's
``system`` sandbox and FND's ``agnet`` both pin ``taxonomy_txa`` today. What was missing is
that the READERS never asked: `_txa_options` iterated one sandbox's rows and `_txa_citation`
looked the document up by ``(msn, sandbox, name)``, so a declared pin changed nothing.

Two rules this keeps:

* **a pin is a declaration, not a guess.** A sandbox that declares nothing still gets
  nothing — the honest empty state `_txa_options` already documents. Binding the source
  stays the operator's act, with the verdict in front of them.
* **a borrowed document is read in ITS OWN namespace.** The rule
  `_a document that crosses a namespace needs re-keying` states from the other side: the
  cells do not change meaning because somebody else is reading them, so the namespace comes
  from the OWNER's ``(msn, sandbox)`` pair and never from the consumer's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._shared.utilities import as_text


@dataclass(frozen=True)
class SourcedDocument:
    """What a sandbox found when it asked for a document by name."""

    document: Any = None
    #: The sandbox that OWNS it, and the instance that holds that sandbox.
    sandbox: str = ""
    msn: str = ""
    #: The namespace its cells are addressed in — the owner's, never the consumer's.
    namespace: str = ""
    #: True when it was reached through a declared source rather than held outright.
    declared: bool = False
    #: Why there is none, in the words a refusal can carry.
    why: str = ""

    def __bool__(self) -> bool:
        return self.document is not None


def _known_sandboxes(store: Any, *, tenant_id: str) -> set[str]:
    """Every sandbox name in the store — what splits ``taxonomy_txa`` into its two halves.

    The whole store, deliberately: a pin names another INSTANCE's sandbox as often as its
    own, which is the arrangement `resolve_sources` documents at length ("both farms'
    manifests deliberately pin documents in FND's registrar and taxonomy sandboxes").
    """
    with store._connect() as connection:
        rows = connection.execute(
            "SELECT DISTINCT sandbox FROM documents WHERE tenant_id=? AND sandbox IS NOT NULL",
            (tenant_id,),
        ).fetchall()
    return {as_text(row["sandbox"]) for row in rows if as_text(row["sandbox"])}


def _holders(store: Any, *, tenant_id: str, sandbox: str, name: str) -> list[str]:
    with store._connect() as connection:
        rows = connection.execute(
            "SELECT DISTINCT msn_id FROM documents WHERE tenant_id=? AND sandbox=? AND name=?",
            (tenant_id, sandbox, name),
        ).fetchall()
    return [as_text(row["msn_id"]) for row in rows if as_text(row["msn_id"])]


def _namespace_of(sandbox: str, msn: str) -> str:
    from micyte.core.datum_ops import field_registry as _fr

    try:
        return _fr.namespace_for_sandbox(sandbox, msn_id=msn)
    except KeyError:
        return sandbox


def declared_pins(store: Any, *, tenant_id: str, sandbox: str, msn: str = "") -> tuple[Any, ...]:
    """Every source row this sandbox declares — manifest rows and local-domain pins alike."""
    from micyte.core.sources import local_domain_pins, manifest_rows

    from ._viewscope import read_document
    from .sources_manager import manifest_name_for

    known = _known_sandboxes(store, tenant_id=tenant_id)
    out: list[Any] = []
    for name, parse in ((manifest_name_for(sandbox), manifest_rows),
                        ("lcl_domain", local_domain_pins)):
        document_id = store.document_id_for(
            tenant_id=tenant_id, msn_id=msn, sandbox=sandbox, name=name)
        if not document_id:
            continue
        document = read_document(store, tenant_id=tenant_id, document_id=document_id)
        if document is not None:
            out.extend(parse(document, sandboxes=known))
    return tuple(out)


def sourced_document(
    store: Any, *, tenant_id: str, sandbox: str, name: str, msn: str = "",
) -> SourcedDocument:
    """The document called ``name`` that ``sandbox`` reads — its own, else one it declares.

    Own first, always: a sandbox holding its own copy is answering for itself, and a pin
    cannot outrank that.
    """
    from ._viewscope import read_document

    sandbox, name, msn = as_text(sandbox), as_text(name), as_text(msn)
    if not (sandbox and name):
        return SourcedDocument(why="a sandbox and a document name are needed")
    own = store.document_id_for(tenant_id=tenant_id, msn_id=msn, sandbox=sandbox, name=name)
    if own:
        return SourcedDocument(
            document=read_document(store, tenant_id=tenant_id, document_id=own),
            sandbox=sandbox, msn=msn, namespace=_namespace_of(sandbox, msn))
    pins = [row for row in declared_pins(store, tenant_id=tenant_id, sandbox=sandbox, msn=msn)
            if as_text(getattr(row, "document_name", "")) == name
            and as_text(getattr(row, "sandbox", ""))]
    if not pins:
        return SourcedDocument(
            why=f"{sandbox} holds no {name} document and declares none as a source")
    pin = pins[0]
    owner = as_text(pin.sandbox)
    # A local-domain pin carries WHOSE sandbox in its title; a manifest row does not, so
    # the index answers — and only when exactly one instance holds that pair. Several is
    # the ambiguity the (msn, sandbox) addressing exists for, and a LIMIT-1 guess here
    # would cite a row out of somebody else's books.
    holders = [as_text(getattr(pin, "node", ""))] if as_text(getattr(pin, "node", "")) else \
        _holders(store, tenant_id=tenant_id, sandbox=owner, name=name)
    if len(holders) != 1:
        return SourcedDocument(
            why=(f"{sandbox} declares {owner}_{name} as a source, but "
                 + (f"{len(holders)} instances hold it — the pin does not say which"
                    if holders else "no instance holds it")))
    owner_msn = holders[0]
    document_id = store.document_id_for(
        tenant_id=tenant_id, msn_id=owner_msn, sandbox=owner, name=name)
    if not document_id:
        return SourcedDocument(
            why=f"{sandbox} declares {owner}_{name} as a source, but it resolves to nothing")
    return SourcedDocument(
        document=read_document(store, tenant_id=tenant_id, document_id=document_id),
        sandbox=owner, msn=owner_msn, namespace=_namespace_of(owner, owner_msn), declared=True)


__all__ = ["SourcedDocument", "declared_pins", "sourced_document"]
