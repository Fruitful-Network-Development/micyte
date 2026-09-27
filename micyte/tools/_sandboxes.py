"""The active INSTANCE's sandbox set — the one query two cross-sandbox tools share.

An instance is a set of sandboxes sharing an msn (`micyte.core.instances`), so "which
sandboxes is this operator looking at" is one indexed query against the documents table.
Held here as a primitive because two surfaces declare against it — the rolodex reads
every sandbox's contacts, the unpinned calendar reads every sandbox's logs — and a second
copy of the resolution rule would be free to drift from the first.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text


def instance_msn_and_sandboxes(
    store: Any, *, tenant_id: str, active_sandbox: str
) -> tuple[str, tuple[str, ...]]:
    """``(msn, sandboxes)`` of the ACTIVE instance — the msn the request is scoped to.

    Scope first (`active_instance_msn`, the ContextVar the shell enters), else the msn the
    active sandbox's own documents carry. With neither, the active sandbox alone is the
    honest fallback — a single-sandbox answer is smaller, not wrong.

    The msn is RETURNED, not just consulted: a cross-sandbox reader must re-enter
    ``use_instance(msn)`` around its per-sandbox reads, because the names it iterates
    include ``system`` — four instances' name — and a read outside the scope raises
    AmbiguousSandboxError exactly as it should. The overlay calendar failed live with
    "'system' is held by 4 instances" before this returned what the loop needs.
    """
    from micyte.core.instance_scope import active_instance_msn

    active = as_text(active_sandbox)
    msn = as_text(active_instance_msn())
    if not msn and active:
        with store._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT msn_id FROM documents WHERE tenant_id=? AND sandbox=?",
                (tenant_id, active),
            ).fetchall()
        # ONE holder resolves; several is the ambiguity the (msn, sandbox) addressing
        # exists for — `system` is four instances' name, and a LIMIT-1 guess here would
        # quietly merge somebody else's week into this calendar. No scope + ambiguous
        # name = answer for the active sandbox alone.
        if len(rows) == 1:
            msn = as_text(rows[0]["msn_id"])
    if not msn:
        return "", ((active,) if active else ())
    from micyte.core import archetypes as arc

    with store._connect() as connection:
        rows = connection.execute(
            "SELECT DISTINCT sandbox FROM documents WHERE tenant_id=? AND msn_id=? "
            "ORDER BY sandbox",
            (tenant_id, msn),
        ).fetchall()
    # The archetype LIBRARY is one of FND's sandboxes and is never operator DATA: an
    # archetype is a blank instance, so a cross-sandbox contacts read found the blank
    # `natural_entity_profile` itself and listed it as a phantom contact — measured on
    # the live store, 27 rolodex rows of which 1 was the library's own blank.
    out = tuple(
        as_text(row["sandbox"]) for row in rows
        if as_text(row["sandbox"]) != arc.ARCHETYPE_SANDBOX
    )
    return msn, (out or ((active,) if active else ()))


def instance_sandboxes(store: Any, *, tenant_id: str, active_sandbox: str) -> tuple[str, ...]:
    """The sandbox half of :func:`instance_msn_and_sandboxes`, for callers that are
    already inside the scope."""
    return instance_msn_and_sandboxes(
        store, tenant_id=tenant_id, active_sandbox=active_sandbox)[1]


__all__ = ["instance_msn_and_sandboxes", "instance_sandboxes"]


def sandbox_document_names(
    store: Any, *, tenant_id: str, sandbox: str, msn_id: str = ""
) -> dict[str, str]:
    """``{name: document_id}`` for every document in one sandbox.

    Names only — the whole point is to answer "what does this sandbox hold" without
    reading any of them. The ``documents`` index answers it in one query; folding the
    catalog to ask the same thing costs the 138 MB blob.

    Held here beside :func:`instance_msn_and_sandboxes` because three callers now need it —
    the re-key that moves documents, the verb that files one, and the surface that shows
    which are unfiled — and a second copy of the query would be free to disagree about
    whether the msn is part of the question. It is: every instance keeps a sandbox called
    ``system``.
    """
    params: list[Any] = [tenant_id, sandbox]
    clause = ""
    if msn_id:
        clause = " AND msn_id=?"
        params.append(msn_id)
    with store._connect() as connection:
        rows = connection.execute(
            "SELECT name, document_id FROM documents WHERE tenant_id=? AND sandbox=?"
            + clause, tuple(params)).fetchall()
    return {r["name"]: r["document_id"] for r in rows}
