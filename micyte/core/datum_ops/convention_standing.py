"""Where every tree stands against the local domain convention — the READ half.

TASK-2026-09-11-001 P4. In the published package rather than beside the apply verb,
because the `convention` surface and the `convention` channel draw it and a tool in the
package cannot reach the host's runtime (`micyte` imports no part of `fnd_app`). The
WRITE half — `apply_convention`, which needs the tree writers — is
`fnd_app/instances/_shared/runtime/convention_runtime.py`, and it imports this.

The archetype library's own `lcl_domain` states the convention
(:mod:`local_domain_convention`); every tree pins it in its sources branch as
``<msn>.archetype_lcl_domain``. A pin is a declaration with a hash, so the verdict is the
sources resolver's own: FRESH when the pinned hash is the library tree's current version,
STALE when the library moved, UNPINNED when the tree never declared it, UNVERIFIABLE when
the tree's namespace cannot carry a hash cell (the glyph and taxonomy libraries) — that
last one reported, never counted as behind, as the seed's own rule reads such a source.
Cheap: one document read per tree from its own semantics row, never the catalog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.document_naming import parse_canonical_document_id

from . import local_domain as _ld
from . import local_domain_convention as ldc
from .datum_resolve import as_text

TENANT = "fnd"
FRESH, STALE, UNPINNED, LIBRARY = "fresh", "stale", "unpinned", "library"
#: A pin the tree carries WITHOUT a hash: its namespace cannot express the hash cell (the
#: glyph and taxonomy libraries), so the seed wrote the pin bare — reported, never
#: counted as behind, exactly as the seed's own rule reads such a source.
UNVERIFIABLE = "unverifiable"
BEHIND = (STALE, UNPINNED)


def library_tree(store: Any) -> Any | None:
    """The archetype library's own `lcl_domain` document, or ``None``."""
    from micyte.core import archetypes as arc
    from micyte.core import instance_baseline as baseline

    documents = list(store.read_documents_by_sandbox(
        tenant_id=TENANT, sandbox=arc.ARCHETYPE_SANDBOX))
    return next((d for d in documents if d.canonical_name in baseline.LOCAL_DOMAIN_NAMES), None)


def pin_title(tree: Any) -> str:
    """``<msn>.archetype_lcl_domain`` — the spelling the sources resolver splits."""
    from micyte.core import archetypes as arc

    parsed = parse_canonical_document_id(str(tree.document_id))
    return f"{parsed.msn_id}.{arc.ARCHETYPE_SANDBOX}_{parsed.name}"


def _every_tree(store: Any) -> list[tuple[str, str, str]]:
    """``[(msn, sandbox, document_id)]`` for every local domain the index names."""
    from micyte.core import instance_baseline as baseline

    with store._connect() as connection:
        rows = connection.execute(
            "SELECT msn_id, sandbox, document_id, name FROM documents WHERE tenant_id = ? "
            "ORDER BY msn_id, sandbox", (TENANT,)).fetchall()
    return [(as_text(r["msn_id"]), as_text(r["sandbox"]), as_text(r["document_id"]))
            for r in rows if as_text(r["name"]) in baseline.LOCAL_DOMAIN_NAMES]


def _pin_of(log: Any, title: str) -> tuple[str, str]:
    """``(slot, recorded hash)`` of the pin titled ``title`` on ``log``, or ``("", "")``."""
    for slot, entry in log.sources().items():
        if as_text(entry.label) == title:
            return slot, as_text(getattr(entry, "hash", ""))
    return "", ""


def convention_status(authority_db: Path, *, sandbox: str = "", msn: str = "") -> dict[str, Any]:
    """Every tree's verdict against the library's tree, cheaply — one document read per
    tree from its own semantics row, never the catalog."""
    from micyte.adapters.sql import open_mos_store
    from micyte.core import archetypes as arc

    store = open_mos_store(authority_db)
    tree = library_tree(store)
    if tree is None:
        return {"ok": False, "error": "this store holds no archetype library tree", "trees": []}
    current = parse_canonical_document_id(str(tree.document_id)).version_hash
    title = pin_title(tree)
    convention = ldc.from_log(_ld.read_log(tree), source=str(tree.document_id))
    expected = ldc.from_constants()
    trees: list[dict[str, Any]] = []
    for tree_msn, tree_sandbox, document_id in _every_tree(store):
        if sandbox and tree_sandbox != sandbox:
            continue
        if msn and tree_msn != msn:
            continue
        if document_id == str(tree.document_id):
            trees.append({"msn": tree_msn, "sandbox": tree_sandbox, "verdict": LIBRARY,
                          "pinned": current, "slot": "",
                          "wants": _wants(_ld.read_log(tree), expected)})
            continue
        document = store.read_authoritative_document(
            tenant_id=TENANT, document_id=document_id, allow_catalog_fallback=False)
        if document is None:
            trees.append({"msn": tree_msn, "sandbox": tree_sandbox, "verdict": "unreadable",
                          "pinned": "", "slot": ""})
            continue
        try:
            log = _ld.read_log(document)
        except Exception as exc:
            trees.append({"msn": tree_msn, "sandbox": tree_sandbox, "verdict": "unreadable",
                          "pinned": "", "slot": "", "why": str(exc)})
            continue
        slot, pinned = _pin_of(log, title)
        verdict = (UNPINNED if not slot else UNVERIFIABLE if not pinned
                   else FRESH if pinned == current else STALE)
        wants = _wants(log, convention)
        if verdict == UNVERIFIABLE and wants:
            verdict = STALE                       # behind on what it CAN be measured on
        trees.append({"msn": tree_msn, "sandbox": tree_sandbox, "verdict": verdict,
                      "pinned": pinned, "slot": slot, "wants": wants})
    counts = {}
    for t in trees:
        counts[t["verdict"]] = counts.get(t["verdict"], 0) + 1
    return {
        "ok": True, "library": str(tree.document_id), "current": current, "pin_title": title,
        "sandbox": arc.ARCHETYPE_SANDBOX, "convention": convention.to_dict(),
        "agrees_with_constants": ldc.disagreements(convention, expected),
        "trees": trees, "counts": counts,
        "summary": (FRESH if not any(t["verdict"] in BEHIND for t in trees)
                    else f"{STALE}({sum(1 for t in trees if t['verdict'] in BEHIND)})"),
    }


def _wants(log: Any, convention: ldc.Convention) -> list[str]:
    """What `apply_convention` would change on ``log``, by name — the dry run's sentence."""
    out: list[str] = []
    have_kinds = {as_text(e.label) for e in log.artifact_kinds().values()}
    for kind in convention.artifact_kinds:
        if kind not in have_kinds:
            out.append(f"mint artifact kind {kind!r}")
    class_kinds = {as_text(e.label): node for node, e in log.children_of(log.class_root).items()} if log.class_root else {}
    for kind in convention.class_kinds:
        if kind not in class_kinds:
            out.append(f"mint class kind {kind!r}")
            for child in convention.vocabularies.get(kind, ()):
                out.append(f"mint {kind}/{child}")
            continue
        have = {as_text(e.label) for e in log.children_of(class_kinds[kind]).values()}
        for child in convention.vocabularies.get(kind, ()):
            if child not in have:
                out.append(f"mint {kind}/{child}")
    glyph_title = {slot: as_text(e.label) for slot, e in log.icons().items()}
    for role, node in _structural_nodes(log).items():
        wanted = convention.structural_glyphs.get(role, "")
        if wanted and log.glyph_slot(wanted) and glyph_title.get(log.icon_of(node), "") != wanted:
            out.append(f"{role} wears {glyph_title.get(log.icon_of(node), '') or 'nothing'!r}, convention says {wanted!r}")
    return out


def _structural_nodes(log: Any) -> dict[str, str]:
    """role -> node, for the structural nodes a tree has (by position, as the reader does)."""
    out: dict[str, str] = {}
    for role, node in ((_ld.ROOT_LABEL, log.root), (_ld.META_LABEL, log.meta_root),
                       ("glyphs", log.glyph_root), ("documents", log.document_root),
                       ("sources", log.source_root), ("artifacts", log.artifact_root),
                       (_ld.CLASS_BRANCH_LABEL, log.class_root),
                       (_ld.OBJECT_BRANCH_LABEL, log.object_root)):
        if node:
            out[role] = node
    for slot, ordinal in dict(log.reserved_slots()).items():
        if ordinal == _ld.ANCHOR_SLOT_ORDINAL:
            out["anchor"] = slot
        elif ordinal == _ld.LOG_SLOT_ORDINAL:
            out["local_domain_slot"] = slot
    for node, entry in log.artifact_kinds().items():
        out[as_text(entry.label)] = node
    if log.class_root:
        for node, entry in log.children_of(log.class_root).items():
            out[as_text(entry.label)] = node
    return out



__all__ = [
    "BEHIND", "FRESH", "LIBRARY", "STALE", "UNPINNED", "UNVERIFIABLE",
    "convention_status", "library_tree", "pin_title",
]
