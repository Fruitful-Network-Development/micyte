"""LCL Editor — the node graph as the navigation AND the selection for editing.

One tool, composed from parts that already exist: the ``local_tree`` on the left is the same
:class:`LocalDomainViewer` payload the FARM tab renders, and the right pane is whatever the
SELECTED node can offer. No new container renderer — a ``composite`` of a ``record_table`` and
``record_form`` panes, all of which the shell already paints.

**The right pane is built for the selection and nothing else.** A tree of seventy nodes would
otherwise ship seventy forms on every render, and the four instance containers would each ship
their whole record table. Selection arrives as the ``lcl_node`` surface query, so an unselected
tree costs exactly the tree.

What a node offers follows from what it IS, which the tree already carries (``node_kind`` from
Phase 1, corrected against the corpus in Phase 2) and which the write path enforces again on the
server:

* a **type** can always define a child type, or declare a child RECORD TYPE — a container
  minted with its own VIEW marker plus a field list written into the ``record_spec`` datum
  document, which is how a new kind of record arrives without a code change. It also offers to
  DELETE itself once nothing but record-less nodes sits beneath it, which is what keeps a record
  type declared with the wrong fields from being permanent;
* a **type carrying a VIEW marker** is an instance container, so it also shows its records and a
  form to add one — unless a bespoke route owns that view, in which case the pane says so by
  name rather than offering a form that would be refused;
* an **instance** is a record: its own row is shown beside a form that EDITS it and one that
  DELETES it, and nothing offers to mint beneath it. A record whose view a bespoke route owns is
  shown read-only and says which route edits it. An instance whose content is an
  ``object_profiles`` row rather than a record row — a barn, a tractor, an employee — shows that
  profile and offers the same delete, since an object's node is marked exactly as a record's is;
* an **unmarked** node offers no verb at all, because the corpus has not said what it is.

The form's fields come from :mod:`micyte.core.datum_ops.record_spec` — the same specification
``create_instance`` validates against, so the form cannot offer a field the writer would reject.
That resolution goes through ``specs_for``, so a container the tenant declared gets a real form
built from its own field list exactly as a built-in one does.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any
from urllib.parse import quote

from micyte.core.datum_ops import local_domain as _ld
from micyte.core.datum_ops.datum_resolve import (
    NODE_KIND_INSTANCE,
    NODE_KIND_TYPE,
)
from micyte.core.datum_ops.node_addrs import parent_of
from micyte.core.datum_ops.record_spec import (
    SPEC_DOCUMENT,
    owner_of,
    read_record,
    spec_for,
    specs_for,
)
from micyte.core.instance_baseline import LCL_DOCUMENT
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from . import _domain_reading as _domain
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._viewscope import local_domain_document_id
from .local_domain_viewer import LocalDomainViewer, build_record_view
from .note_books import LINE_CHARS as _LINE_CHARS
from .note_books import NOTE_CHAR_BUDGET as _NOTE_CHAR_BUDGET
from .samras_structure_viewer import SamrasStructureViewer

_SCHEMA = "mycite.v2.portal.workbench.tool.lcl_editor.v1"
#: The SAMRAS STRUCTURE the local domain rides. Not the document's name — the two
#: were one constant until 2026-08-20, which is how a document rename would have
#: silently re-pointed a structure lookup.
_LCL_STRUCTURE = "lcl"
_SELECT_PARAM = "lcl_node"
_AGRO_ROUTE = "/portal/api/v2/agro"
_NOTES_ROUTE = "/portal/api/v2/notes"

#: Every write the surface posts, stated once and carried in the payload. The client holds
#: no route of its own: a URL hardcoded in JavaScript is a second declaration of where a
#: write goes, and the register that gates these actions cannot see it.
ROUTES = {
    "create_document": f"{_AGRO_ROUTE}/create_document",
    "attach_document": f"{_AGRO_ROUTE}/attach_document",
    "detach_document": f"{_AGRO_ROUTE}/detach_document",
    "file_artifact": f"{_AGRO_ROUTE}/file_artifact",
    "set_node_icon": f"{_AGRO_ROUTE}/set_node_icon",
    "save_note": f"{_NOTES_ROUTE}/save_note",
    "rename_node": f"{_AGRO_ROUTE}/rename_node",
    "move_node": f"{_AGRO_ROUTE}/move_node",
    "delete_node": f"{_AGRO_ROUTE}/delete_node",
    "insert_node": f"{_AGRO_ROUTE}/insert_node",
    "define_type": f"{_AGRO_ROUTE}/define_type",
    "define_root_type": f"{_AGRO_ROUTE}/define_root_type",
    "save_node_note": f"{_NOTES_ROUTE}/save_node_note",
}


def _writings(db: Path | None, sandbox: str) -> tuple[dict[str, Any], Any, str]:
    """``(writings, log, anchor name)`` — this sandbox's documents on its tree, and how.

    The one read, through the one read model. An empty answer for a missing store is the
    honest shape rather than an error: the tree still renders, and every node simply says
    it holds nothing, which is true.

    The LOG comes back beside the writings because the surface needs both and they are one
    read of one document: which slots exist, what they are titled, and which nodes point at
    them. A sandbox with no meta branch answers with an empty log, and every caller below
    treats that as "this tree names its documents the old way" rather than as an error.
    """
    empty: dict[str, Any] = {"by_node": {}, "options": {}, "unassigned": []}
    blank = _ld.LocalDomainLog(entries={}, meta_root="")
    if db is None or not sandbox:
        return empty, blank, ""
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
    from micyte.core import archetypes as arc

    store = SqliteSystemDatumStoreAdapter(Path(db))
    log = _ld.read_log(_lcl_document(store, sandbox))
    library = store.read_documents_by_sandbox(
        tenant_id="fnd", sandbox=arc.ARCHETYPE_SANDBOX)
    return (
        _domain.read_writings(
            store, tenant_id="fnd", sandbox=sandbox,
            registry=arc.registry_for(library), log=log),
        log,
        _anchor_name(store, sandbox),
    )


def _icon_faces(db: Path | None, sandbox: str, log: Any) -> dict[str, dict[str, Any]]:
    """``{icon slot: {title, paths}}`` — every glyph this sandbox holds, DECODED.

    Read here rather than by the client, for the reason every other denotation on this
    surface is: the rows are the drawing, and a client that decoded them would be a second
    implementation of the codec — one that could disagree with the one the store validates
    against.

    A glyph whose rows do not decode is SKIPPED and its slot simply has no face. The tree
    then draws that node with no icon, which is true, rather than with a broken one.
    """
    faces: dict[str, dict[str, Any]] = {}
    slots = getattr(log, "icons", lambda: {})()
    if db is None or not sandbox or not slots:
        return faces
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
    from micyte.core.datum_ops import glyph as _glyph

    store = SqliteSystemDatumStoreAdapter(Path(db))
    # TARGETED reads, by name, one per icon. `read_documents_by_sandbox` was the first cut
    # and it is the wrong tool here: the registrar holds 482 documents and this needs one
    # of them, so the domain surface paid for the whole sandbox on every paint. Measured
    # after: the first navigation went from 44 s to under a second.
    with store._connect() as connection:
        rows = connection.execute(
            "SELECT name, document_id FROM documents WHERE tenant_id=? AND sandbox=? "
            f"AND name IN ({','.join('?' * len(slots))})",
            ("fnd", sandbox, *sorted(slots)),
        ).fetchall()
    ids = {row["name"]: row["document_id"] for row in rows}
    for slot, entry in slots.items():
        document_id = ids.get(slot)
        if document_id is None:
            continue
        paths = _face_paths(str(db), str(document_id))
        if paths is None:
            continue
        faces[slot] = {"title": entry.label, "view_box": _glyph.VIEW_BOX, "paths": list(paths)}
    return faces


@functools.lru_cache(maxsize=512)
def _face_paths(db: str, document_id: str) -> tuple[dict[str, Any], ...] | None:
    """The decoded paths of one glyph document, cached BY DOCUMENT ID.

    The operator's "loaded or cached as SVGs" (2026-09-08). A canonical id embeds the
    document's content hash, so a hit is exact and a republished drawing is a miss by
    construction — no invalidation to get wrong. Every sandbox now holds the eleven
    canonical drawings as its OWN documents, so without this the same eleven paths were
    decoded once per sandbox per paint; with it they are decoded once per process per
    document. ``None`` for a document that is missing or does not decode, which the
    caller reads as "no face" — true, rather than a broken one.
    """
    from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
    from micyte.core.datum_ops import glyph as _glyph

    document = SqliteSystemDatumStoreAdapter(Path(db)).read_authoritative_document(
        tenant_id="fnd", document_id=document_id)
    if document is None:
        return None
    try:
        drawing = _glyph.glyph_of(getattr(document, "rows", ()) or ())
    except _glyph.GlyphError:
        return None
    return tuple({"d": path.to_text(), "fill": bool(path.fill)} for path in drawing.paths)


def _anchor_name(store: Any, sandbox: str) -> str:
    """What this sandbox calls its anchor — ``anchor`` or ``anthology``.

    Slot ``1-1`` names it, and which literal it is depends on when the sandbox was made,
    so the reserved slot cannot resolve without asking. Asked through the documents index,
    which is one query and no rows.
    """
    from micyte.core.document_naming import ANCHOR_DOCUMENT_NAMES
    from micyte.tools._sandboxes import sandbox_document_names

    try:
        held = sandbox_document_names(store, tenant_id="fnd", sandbox=sandbox)
    except Exception:
        return ""
    for name in sorted(set(held) & ANCHOR_DOCUMENT_NAMES):
        return name
    return ""


def _lcl_document(store: Any, sandbox: str) -> Any:
    """The sandbox's own local domain, read by NAME — or ``None``.

    By name through the documents index rather than by walking the catalog: the surface
    already pays one sandbox read for the writings, and a second catalog fold to find one
    document would cost the 138 MB blob to answer a question the index answers.
    """
    from micyte.tools._viewscope import read_document

    document_id = local_domain_document_id(store, tenant_id="fnd", sandbox=sandbox)
    if not document_id:
        return None
    return read_document(store, tenant_id="fnd", document_id=document_id)


def _notice(title: str, text: str) -> dict[str, Any]:
    """A pane that explains itself. Rendered by the shared record_table renderer's empty state."""
    return {"schema": _SCHEMA, "container": "record_table", "title": title,
            "columns": [], "rows": [], "row_count": 0, "count_label": "", "empty_text": text}


def _insert_node_form(sandbox: str, node: str, label: str) -> dict[str, Any]:
    """Insert a grouping node ABOVE the selection — the SAMRAS re-address verb.

    The name-first tree's remedy for extending beneath a leaf: the new node takes
    this node's address and this node (with its whole subtree, notes following)
    becomes its first child.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Insert a group above {label or node}",
        "fields": [{
            "key": "label",
            "label": (f"Group name — takes address {node}; "
                      f"{label or node} becomes {node}-1"),
            "type": "text", "value": "",
        }],
        "submit_label": "Insert group",
        "submit_action": {"route": f"{_AGRO_ROUTE}/insert_node", "sandbox_id": sandbox,
                          "success_label": "Inserted", "fixed": {"node": node}},
    }


def _root_branch_form(sandbox: str) -> dict[str, Any]:
    """Name a new TOP-LEVEL branch — the only verb that widens the tree at its root.

    Offered on a root selection, because that is where "beside this one" is a thing a
    person can see. Everywhere else it would be an action whose effect appears somewhere
    the operator is not looking.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Name a top-level branch",
        "fields": [{
            "key": "label",
            "label": "Branch name — a new root beside this one, at the next free number",
            "type": "text", "value": "",
        }],
        "submit_label": "Add branch",
        "submit_action": {"route": f"{_AGRO_ROUTE}/define_root_type",
                          "sandbox_id": sandbox, "success_label": "Added"},
    }


def _sibling_form(sandbox: str, node: str, label: str) -> dict[str, Any]:
    """Name a sibling — define_type fixed to the PARENT, the name-first tree's other
    half ('create nodes by giving them a name … either as a sibling or child')."""
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Define a type beside {label or node}",
        "fields": [{"key": "label", "label": "Type name", "type": "text", "value": ""}],
        "submit_label": "Define sibling",
        "submit_action": {"route": f"{_AGRO_ROUTE}/define_type", "sandbox_id": sandbox,
                          "fixed": {"parent_node": parent_of(node)}},
    }


def _define_type_form(sandbox: str, node: str, label: str) -> dict[str, Any]:
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Define a type under {label or node}",
        "fields": [{"key": "label", "label": "Type name", "type": "text", "value": ""}],
        "submit_label": "Define type",
        "submit_action": {"route": f"{_AGRO_ROUTE}/define_type", "sandbox_id": sandbox,
                          "fixed": {"parent_node": node}},
    }


def _define_record_type_form(sandbox: str, node: str, label: str) -> dict[str, Any]:
    """Declare a record type in data — the form that makes a new record type need no Python.

    The field list is one textarea, one field per line, because the number of fields is the
    thing the tenant is choosing: a fixed set of inputs cannot express it, and a repeating-row
    widget would be a bespoke renderer for one form. The syntax is stated in the placeholder
    and parsed server-side by ``record_spec.parse_field_lines``, so the client stays dumb and
    the rules live with the format.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Declare a record type under {label or node}",
        "fields": [
            {"key": "label", "label": "Record type name", "type": "text", "value": ""},
            {"key": "fields", "label": "Fields — one per line, 'name* | Label' (* = required)",
             "type": "textarea", "value": "",
             "placeholder": "name* | Supplier name\nemail | Email\nlead_time_days | Lead time"},
        ],
        "submit_label": "Declare record type",
        "submit_action": {"route": f"{_AGRO_ROUTE}/define_record_type", "sandbox_id": sandbox,
                          "fixed": {"parent_node": node}},
    }


def _delete_type_form(sandbox: str, node: str, label: str, declares: str) -> dict[str, Any]:
    """Remove this container — offered only when the tree says nothing but husks is under it.

    The tool asks the cheap question the TREE can answer (is any descendant a type, an
    unclassified node, or a node with a record in this view's table?); the server asks the whole
    one, over every document in the sandbox. That asymmetry is deliberate and is the same posture
    the confirmation dialog takes: this is the affordance, the write path is the gate. It means
    the button can occasionally be refused with a reason — never that a refusal is silent.
    """
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Delete {label or node}",
        "fields": [],
        "submit_label": "Delete type",
        "submit_action": {
            "route": f"{_AGRO_ROUTE}/delete_type", "sandbox_id": sandbox,
            "fixed": {"node": node}, "danger": True, "success_label": "Deleted",
            "confirm": {"expect": label or node, "key": "confirm",
                        "text": f"This removes the type node {node}"
                                + (f" and the {declares!r} record type it declares"
                                   if declares else "")
                                + ". It cannot be undone."},
        },
    }


def _type_delete_pane(sandbox: str, node: str, label: str, tree: dict[str, Any],
                      record_ids: set[str], declares: str) -> dict[str, Any] | None:
    """The delete offer for a type node — a form, an explanation, or nothing.

    Three outcomes because the two reasons a delete cannot happen are not alike:

    * the container HOLDS something — a child type, an unclassified node, a record. Nothing is
      drawn: the pane already lists what is in there, so a button explaining itself would be
      restating what the operator can see;
    * the container is empty but is not the LAST child of its parent, so dropping it would leave
      non-contiguous ordinals and the lcl-SAMRAS magnitude would not compile. Here the absence
      needs explaining — the container looks removable and is not — so this says why instead;
    * otherwise, the form.

    Both questions are answered from the TREE, which the payload already carries, so no extra
    read is paid for a selection. The write path asks them again over every document in the
    sandbox: this is the affordance, and the affordance must not offer what would be refused.
    """
    for entry in tree.get("nodes", ()):
        slug = _as_text(entry.get("full_slug"))
        if not slug.startswith(node + "-"):
            continue
        if _as_text(entry.get("node_kind")) != NODE_KIND_INSTANCE or slug in record_ids:
            return None
    later = _later_siblings(node, tree)
    if later:
        return _notice(
            f"Delete {label or node}",
            f"{node} is not the last child of {parent_of(node)} — {', '.join(later[:3])} "
            f"{'come' if len(later) > 1 else 'comes'} after it — so removing it would leave its "
            "container with non-contiguous child ordinals, which the lcl-SAMRAS magnitude "
            "refuses. It becomes removable once those are gone.")
    return _delete_type_form(sandbox, node, label, declares)


def _later_siblings(node: str, tree: dict[str, Any]) -> list[str]:
    """Siblings of ``node`` with a higher ordinal — what the contiguity rule protects."""
    parent = parent_of(node)

    def ordinal(address: str) -> int:
        try:
            return int(address.rpartition("-")[2] or address)
        except ValueError:
            return 0

    mine = ordinal(node)
    return sorted((slug for slug in (_as_text(n.get("full_slug")) for n in tree.get("nodes", ()))
                   if parent_of(slug) == parent and ordinal(slug) > mine), key=ordinal)


def _create_instance_form(sandbox: str, node: str, label: str, spec: Any) -> dict[str, Any]:
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"New record in {label or node}",
        "fields": [
            {"key": field.name, "type": "text", "value": "",
             "label": field.display + (" *" if field.required else "")}
            for field in spec.fields
        ],
        "submit_label": "Create record",
        # `fields_key` nests the collected inputs under `fields`, which is the shape
        # create_instance takes; `fixed` carries the node the tree selected.
        "submit_action": {"route": f"{_AGRO_ROUTE}/create_instance", "sandbox_id": sandbox,
                          "fixed": {"type_node": node}, "fields_key": "fields"},
    }


def _save_instance_form(sandbox: str, node: str, label: str, spec: Any,
                        values: dict[str, str]) -> dict[str, Any]:
    """The record's own values, editable. Keyed by NODE — the address is not the identity."""
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Edit {label or node}",
        "fields": [
            {"key": field.name, "type": "text", "value": values.get(field.name, ""),
             "label": field.display + (" *" if field.required else "")}
            for field in spec.fields
        ],
        "submit_label": "Save record",
        "submit_action": {"route": f"{_AGRO_ROUTE}/save_instance", "sandbox_id": sandbox,
                          "fixed": {"node": node}, "fields_key": "fields"},
    }


def _delete_instance_form(sandbox: str, node: str, label: str, spec: Any,
                          values: dict[str, str]) -> dict[str, Any]:
    """The one destructive form on this surface, so it asks for the record's title back.

    The confirmation is declared, not drawn: `submit_action.confirm` sends the button through the
    shared typed-confirmation dialog the Objects panel's delete uses, so the two surfaces present
    one gate rather than two that drift. `expect` names the exact text — the pane shows the
    record's title and its node label side by side, and leaving the operator to work out which is
    meant is how a confirmation becomes a formality.
    """
    expected = _as_text(values.get(spec.title_field, "")).strip() or label or node
    return {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Delete {label or node}",
        "fields": [],
        "submit_label": "Delete record",
        # No `fields_key`: delete_instance takes the confirmation flat, beside the node.
        "submit_action": {
            "route": f"{_AGRO_ROUTE}/delete_instance", "sandbox_id": sandbox,
            "fixed": {"node": node}, "danger": True, "success_label": "Deleted",
            "confirm": {"expect": expected, "key": "confirm",
                        "text": f"This deletes the {spec.document} record on {node}. "
                                "It cannot be undone."},
        },
    }


def _object_pane(db: Path | None, sandbox: str, node: str, label: str) -> dict[str, Any] | None:
    """A typed object's profile, a note naming its editor, and the delete — or ``None``.

    An object's node is an INSTANCE marked exactly like a record's; what differs is where its
    content lives (an ``object_profiles`` row rather than a record row). So the tree can offer the
    same thing it offers a record, and until now it offered nothing: the pane fell through to
    "this record's container has no record table", which is true and useless.

    Editing stays with the Objects panel — the same posture this pane already takes for `invoice`
    and `product`. A typed object carries a kind, free attributes and sometimes drawn geometry,
    and a second editor for that shape is how two writers of one document drift apart. Delete is
    different: it is one verb over one node, already generic, already gated.
    """
    profile = _object_profile(db, sandbox, node)
    if profile is None:
        return None
    attrs = profile.get("attrs") or {}
    rows = [{"field": "Node", "value": node}, {"field": "Name", "value": profile.get("name", "")},
            {"field": "Kind", "value": profile.get("kind", "")}]
    rows += [{"field": key, "value": value} for key, value in sorted(attrs.items())]
    shown = {"schema": _SCHEMA, "container": "record_table",
             "title": f"{profile.get('name') or label or node} — object",
             "columns": ["field", "value"], "rows": rows, "row_count": len(rows),
             "count_label": f"{profile.get('kind') or 'object'}", "empty_text": ""}
    name = _as_text(profile.get("name")) or label or node
    return {"schema": _SCHEMA, "container": "composite", "direction": "column", "panes": [
        {"panel_payload": shown},
        {"panel_payload": _notice(
            "Object profile",
            "The name, kind and attributes of a typed object are edited in the Infrastructure & "
            "People panel, which knows its shape. This node can be deleted from here.")},
        {"panel_payload": {
            "schema": _SCHEMA, "container": "record_form",
            "title": f"Delete {name}", "fields": [], "submit_label": "Delete object",
            "submit_action": {
                "route": f"{_AGRO_ROUTE}/delete_object", "sandbox_id": sandbox,
                "fixed": {"object_node": node}, "danger": True, "success_label": "Deleted",
                "confirm": {"expect": name, "key": "confirm",
                            "text": f"This removes the object on {node} and any geometry it "
                                    "owns. It cannot be undone."},
            },
        }},
    ]}


def _object_profile(db: Path | None, sandbox: str, node: str) -> dict[str, Any] | None:
    """This node's ``object_profiles`` row, read through the reader every object surface uses.

    `build_object_rows` is what the Objects panel and the micyte.com export both read, and what
    `delete_object` now agrees with about an object's displayed name — so the text this pane asks
    the operator to type is the text the server will expect.
    """
    from ._archetype import find_named_document, read_sandbox_catalog
    from .object_profiles_view import build_object_rows

    docs, err = read_sandbox_catalog(db, sandbox=sandbox)
    if err:
        return None
    document = find_named_document(docs, sandbox=sandbox, name="object_profiles")
    if document is None:
        return None
    return next((row for row in build_object_rows(document)
                 if _as_text(row.get("node")) == node), None)


def _instance_pane(db: Path | None, sandbox: str, node: str, label: str,
                   views: dict[str, str]) -> dict[str, Any]:
    """A record's own row, plus the form that edits it when this surface may write it."""
    view = views.get(parent_of(node), "")
    table = build_record_view(view, authority_db_file=db, sandbox_id=sandbox) if view else None
    if table is None:
        # A view a bespoke route owns says so even with no table to show — the ledger
        # tokens lost their bespoke tables in the old-model pane cleanup, and the
        # refusal must not silently degrade into "nothing to show".
        owned = owner_of(view) if view else ""
        if owned:
            return _notice(label or node,
                           f"Records of the {view} view are written by {owned}, "
                           "not from the tree.")
        # No record table — but an object is an instance too, and its content is elsewhere.
        objects = _object_pane(db, sandbox, node, label)
        if objects is not None:
            return objects
        return _notice(label or node,
                       "This record's container has no record table, so there is nothing to show.")
    owner = owner_of(view)
    rows = [r for r in table.get("rows", []) if _as_text(r.get("lcl_id")) == node]
    if not rows:
        return _notice(label or node,
                       f"{node} is marked a record, but no row in the {view} table names it. " +
                       (f"Records of this view are written by {owner}, not from the tree."
                        if owner else
                        "Entering it from its container will adopt this node rather than "
                        "duplicate it."))
    shown = {**table, "title": f"{label or node} — record", "rows": rows, "row_count": len(rows),
             "count_label": "1 record"}

    if owner:
        # The row is shown, but editing it belongs to the route that knows its shape.
        return {"schema": _SCHEMA, "container": "composite", "direction": "column", "panes": [
            {"panel_payload": shown},
            {"panel_payload": _notice(f"{view} records",
                                      f"Records of this view are edited by {owner}, not here.")},
        ]}
    spec = _spec_for_view(db, sandbox, view)
    found = _read_record(db, sandbox, spec, node) if spec is not None else None
    if found is None:
        return shown
    return {"schema": _SCHEMA, "container": "composite", "direction": "column", "panes": [
        {"panel_payload": shown},
        {"panel_payload": _save_instance_form(sandbox, node, label, spec, found[1])},
        {"panel_payload": _delete_instance_form(sandbox, node, label, spec, found[1])},
    ]}


def _read_record(db: Path | None, sandbox: str, spec: Any, node: str) -> Any:
    """This record's stored values, read through the SAME parser the writer inverts.

    Prefilling from the rendered table would work today and break the moment a normalizer
    renamed a column; the row format has one reader, and this is it.
    """
    from ._archetype import find_named_document, read_sandbox_catalog

    docs, err = read_sandbox_catalog(db, sandbox=sandbox)
    if err:
        return None
    return read_record(find_named_document(docs, sandbox=sandbox, name=spec.document), spec, node)


def _spec_for_view(db: Path | None, sandbox: str, view: str) -> Any:
    """The record shape behind a VIEW token — built in, or declared by this sandbox's data.

    Read only when a selected node actually carries a view, so an unselected tree never pays
    for the catalog read.
    """
    builtin = spec_for(view)
    if builtin is not None:
        return builtin
    from ._archetype import find_named_document, read_sandbox_catalog

    docs, err = read_sandbox_catalog(db, sandbox=sandbox)
    if err:
        return None
    spec_doc = find_named_document(docs, sandbox=sandbox, name=SPEC_DOCUMENT)
    return specs_for({SPEC_DOCUMENT: spec_doc}, sandbox_id=sandbox).get(view)


def _record_panes(db: Path | None, sandbox: str, node: str, tree: dict[str, Any],
                  noted: Any = ()) -> list[dict[str, Any]]:
    """The RECORD half of a selection — the table, the create form, the declaration.

    Everything a node offers because of what it CONTAINS rather than because of where it
    sits. The structural half (rename, re-parent, insert, add, move, delete) and the
    node's own writing moved onto the domain card, where they are one gesture each; this
    is what is left, and it is only ever built for a node that actually carries records.

    Returned as a list so an empty one costs nothing: a note tree — every Oveure sandbox
    — never pays for a record pane it has no records for.
    """
    by_slug = {_as_text(n.get("full_slug")): n for n in tree.get("nodes", ())}
    selected = by_slug.get(node)
    if selected is None:
        return []
    label = _as_text(selected.get("label"))
    kind = _as_text(selected.get("node_kind"))
    views = {_as_text(n.get("full_slug")): _as_text(n.get("record_view"))
             for n in tree.get("nodes", ()) if _as_text(n.get("record_view"))}

    if kind == NODE_KIND_INSTANCE:
        inner = _instance_pane(db, sandbox, node, label, views)
        if inner.get("container") == "composite":
            return list(inner.get("panes") or ())
        return [{"panel_payload": inner}]
    if kind != NODE_KIND_TYPE:
        return [{"panel_payload": _notice(
            label or node,
            "The corpus has not classified this node, so there is nothing safe to create "
            "here. Classify it first (audit_lcl_node_kinds).")}]

    panes: list[dict[str, Any]] = []
    view = _as_text(selected.get("record_view"))
    record_ids: set[str] = set()
    spec = None
    if not view:
        # Declaring a record type in DATA is what lets a new record shape arrive without a
        # code change, and it is offered on a plain type node because that is where a
        # container is declared. Kept out of the card on purpose: the card is the four
        # gestures a tree needs, and a field-list textarea is not one of them.
        #
        # Not offered on a node that holds a writing: the declaration MINTS a child, and a
        # node with a writing takes none. Offering it there would be a form the write path
        # refuses — the affordance must not promise what the gate declines.
        if node in noted:
            return []
        return [{"panel_payload": _define_record_type_form(sandbox, node, label)}]
    if view:
        owner = owner_of(view)
        spec = _spec_for_view(db, sandbox, view)
        table = build_record_view(view, authority_db_file=db, sandbox_id=sandbox)
        if table is not None:
            record_ids = {_as_text(r.get("lcl_id")) for r in table.get("rows", ())}
            panes.append({"label": f"{label or node} records", "panel_payload": table})
        if owner:
            panes.append({"panel_payload": _notice(
                f"{view} records",
                f"Records of this view are written by {owner}, not from the tree.")})
        elif spec is not None:
            panes.append({"panel_payload": _create_instance_form(sandbox, node, label, spec)})
        else:
            panes.append({"panel_payload": _notice(
                f"{view} records",
                f"No record specification for view {view!r} yet. Declaring a record type of "
                "that name here would give it one.")})
        if not owner:
            # Only where `delete_type` would actually accept the write: a view a bespoke
            # route owns is refused by that verb BY NAME, and a button that always
            # refuses is the affordance promising what the gate declines.
            #
            # A type with NO view offers no form here at all — the card's delete is the
            # verb for one, and it re-keys the siblings that follow where `delete_type`
            # can only refuse them. This form survives for the one case the card hands
            # off: a container whose record-type DECLARATION goes with it.
            declares = view if spec_for(view) is None else ""
            delete = _type_delete_pane(sandbox, node, label, tree, record_ids, declares)
            if delete is not None:
                panes.append({"panel_payload": delete})
    return panes


def _ledger(log: Any, writings: dict[str, Any]) -> dict[str, Any]:
    """The document branch, as the surface needs it: where, what kinds, which slots.

    Empty ``root`` is the honest answer for a tree that has not adopted the log — every
    document control then hides rather than offering a write the runtime would refuse.
    """
    root = _as_text(getattr(log, "slot_root", ""))
    if not root:
        return {"root": "", "kinds": [], "slots": [], "unassigned": 0}
    by_name = {_as_text(entry.get("name")): entry for entry in _every(writings)}
    # ONE pass for "which node denotes each slot". Asking the log per slot is the same
    # answer computed n times, and this list is what the attach picker and the unassigned
    # count are both built from.
    holder = {entry.slot: node for node, entry in log.entries.items() if entry.slot}
    reserved = log.reserved_slots()
    slots = [
        {"slot": slot, "title": entry.label, "node": holder.get(slot, ""),
         # RESERVED slots are LISTED and not offered. The operator put the anchor and the
         # log in the namespace deliberately ("1-1 is the anchor file and 1-2 is the
         # lcl_domain file"), so hiding them would be hiding two of the sandbox's
         # documents; what the surface withholds is attaching or deleting them.
         "reserved": slot in reserved,
         "kind": _as_text((by_name.get(slot) or {}).get("kind")),
         "preview": _as_text((by_name.get(slot) or {}).get("preview"))}
        for slot, entry in log.slots().items()
    ]
    # THE OTHER TWO THINGS A NODE MAY DENOTE (2026-09-08): a source pin and an artifact,
    # each a slot on its own branch. Offered beside the documents, grouped, so the attach
    # picker is one picker over one denotation — the branch the chosen slot sits under
    # is what tells the log which reading to give it.
    holder_any = {ref: node for node, entry in log.entries.items()
                  for ref in (entry.slot, entry.artifact, entry.source) if ref}
    sources = [
        {"slot": slot, "title": entry.label, "node": holder_any.get(slot, ""),
         "hash": _as_text(getattr(entry, "hash", ""))}
        for slot, entry in getattr(log, "sources", dict)().items()
    ]
    kinds_of = {kind: entry.label for kind, entry in getattr(log, "artifact_kinds", dict)().items()}
    artifacts = [
        {"slot": slot, "title": entry.label, "node": holder_any.get(slot, ""),
         "kind": kinds_of.get(parent_of(slot), "")}
        for slot, entry in getattr(log, "artifacts", dict)().items()
    ]
    return {
        "root": root,
        "kinds": [{"value": token, "label": label}
                  for token, (_archetype, label) in sorted(_ld.DOCUMENT_KINDS.items())],
        "slots": slots,
        "sources": sources,
        "artifacts": artifacts,
        "unassigned": sum(
            1 for slot in slots if not slot["node"] and not slot["reserved"]),
    }


def _every(writings: dict[str, Any]) -> list[dict[str, Any]]:
    """Every writing in the sandbox, however it is filed. One list, three buckets."""
    return [
        *writings["by_node"].values(),
        *[entry for bucket in writings["options"].values() for entry in bucket],
        *writings["unassigned"],
    ]


def _card(
    db: Path | None, sandbox: str, node: str, tree: dict[str, Any],
    writings: dict[str, Any], actions: dict[str, str], log: Any = None,
    anchor_name: str = "",
) -> dict[str, Any]:
    """Everything the SELECTED node is and can become — one card, built for one node.

    The domain surface's whole editing model. A node's address, its label and its parent
    are edited in place because all three are facts about the node itself; everything that
    changes the SHAPE of the tree is an explicit action with its own confirmation. The
    node's writing rides here too, because selecting a node in the graph to edit the
    document associated with it is what this surface is for.

    Built only for the selection — a tree of seventy nodes ships one card, the rule the
    split pane established and the reason an unselected tree costs exactly the tree.
    """
    by_slug = {_as_text(n.get("full_slug")): n for n in tree.get("nodes", ())}
    selected = by_slug.get(node)
    if selected is None:
        return {"node": node, "missing": True,
                "why": f"{node} is not a node of this tree."}

    label = _as_text(selected.get("label"))
    kind = _as_text(selected.get("node_kind"))
    parent = parent_of(node)
    if kind not in (NODE_KIND_TYPE, NODE_KIND_INSTANCE):
        # The existing refusal, kept whole: an UNMARKED node is one the corpus has never
        # said anything about, and a surface that offered to write on it, name children
        # under it or move it would be organizing by guess. The card explains instead of
        # showing controls that would each be a different kind of wrong.
        return {"node": node, "label": label, "kind": "unclassified",
                "parent": parent, "unclassified": True,
                "why": ("The corpus has not classified this node, so there is nothing "
                        "safe to do here yet. Classify it first "
                        "(audit_lcl_node_kinds).")}
    subtree = sorted(slug for slug in by_slug
                     if slug != node and slug.startswith(node + "-"))
    children = sorted(slug for slug in by_slug if parent_of(slug) == node)
    own = writings["by_node"].get(node)
    options = list(writings["options"].get(node, ()))
    if log is not None and log.is_document_node(node):
        # A SLOT is the document. Selecting one shows what it holds — which is not what
        # `by_node` answers, because that is keyed on the node POINTING at a document and
        # a slot points at nothing. Found by name, which is what a slot is called.
        own = next((entry for entry in _every(writings)
                    if _as_text(entry.get("name")) == node), None)
        options = []

    # Which nodes could take this one. A TYPE that is neither this node nor inside it,
    # and that holds no writing of its own — the leaf rule, asked here so the picker
    # cannot offer a parent `move_node` would refuse.
    # A SLOT hangs off the DOCUMENT branch, which on a subdivided tree is `1-2` and not
    # the meta root. Asked of the log, because "where slots hang" is a fact about the tree
    # and every reader that spelled it as `parent == meta_root` went silently blind.
    meta_root = _as_text(getattr(log, "meta_root", ""))
    structural = log.branch_roots() if log is not None else frozenset()
    on_branch = log is not None and log.is_document_node(node)
    # Two nodes are offered NOWHERE, and for the same reason `move_node` refuses them:
    #
    # * a SLOT is a document filed on the reserved branch. Moving it into the tree would
    #   take it off `log.slots()`, and the surface would stop listing it while the
    #   document sat there perfectly intact;
    # * the BRANCH itself is where every document in the sandbox is filed. Filing it under
    #   a topic would put them all inside one.
    parents: list[dict[str, str]] = []
    if not on_branch and node not in structural:
        parents = [{"value": "", "label": "(top level)"}] if parent else []
        for slug, entry in sorted(by_slug.items()):
            if slug == node or slug.startswith(node + "-") or slug == parent:
                continue
            if _as_text(entry.get("node_kind")) != NODE_KIND_TYPE:
                continue
            if slug in writings["by_node"]:
                continue
            if slug in structural or (log is not None and log.is_document_node(slug)):
                continue
            parents.append({"value": slug,
                            "label": f"{slug}  {_as_text(entry.get('label')) or slug}"})

    # What a delete would destroy, NAMED. The same list the server builds its refusal
    # from, so the dialog asks for exactly what the gate expects.
    doomed = [own["name"]] if own else []
    doomed += [entry["name"] for entry in options]
    for slug in subtree:
        if slug in writings["by_node"]:
            doomed.append(writings["by_node"][slug]["name"])
        doomed += [entry["name"] for entry in writings["options"].get(slug, ())]

    return {
        "node": node,
        "label": label,
        "kind": kind or "unclassified",
        "parent": parent,
        "parent_label": _as_text((by_slug.get(parent) or {}).get("label")),
        "parents": parents,
        "children": children,
        "subtree": len(subtree),
        "note": _writing_block(own, sandbox, node, log),
        "options": [
            {**_writing_block(entry, sandbox, node, log), **entry,
             "action": _domain.resolve_action(entry["text"], actions),
             "reference": _domain.action_reference(entry["text"])}
            for entry in options
        ],
        "is_decision": bool(options),
        # A slot IS a document. Selecting one shows what it holds and offers to retitle or
        # delete it; it never offers to hang a document on it, which is the one thing a
        # document cannot do.
        "is_slot": on_branch,
        "denotes": _as_text(getattr(log, "slot_of", lambda _n: "")(node)),
        # Where the DOCUMENT is, when this node addresses one. Selecting a document node
        # on the tree opens it at the Compendium's document level rather than in a second
        # inline reader here — that level already has the raw datum tab and the crumbs
        # back out to this tree.
        "open": _document_href(sandbox, _document_id_of(
            _document_of(node, on_branch, log, anchor_name),
            {_as_text(entry.get("name")): entry for entry in _every(writings)})),
        # A RESERVED slot is the anchor or the log. Listed, and never retitled or deleted:
        # every reader of a sandbox finds those two by name.
        "reserved": bool(on_branch and getattr(log, "is_reserved", lambda _s: False)(node)),
        # The glyph this node wears, and whether it may wear one. A node on the ICON
        # branch is a glyph itself; giving it an icon would be a picture of a picture.
        "icon": _as_text(log.icon_of(node)) if log is not None else "",
        "can_icon": bool(log is not None and log.subdivided
                         and not log.is_icon_node(node) and not log.is_structural(node)),
        # A node holding a writing takes no children (the leaf rule) — stated here rather
        # than left for the client to re-derive, because the server enforces it again and
        # two derivations of one rule drift.
        "can_child": kind == NODE_KIND_TYPE and not own and not on_branch,
        # …and the same rule from the other side: a node with children says nothing of its
        # own. Under the log a document is ATTACHED rather than typed into, so what the
        # card offers is "add" and "attach", both of which need a title and a kind.
        "can_document": bool(meta_root) and kind == NODE_KIND_TYPE and not own
        and not on_branch and node not in structural and not children,
        "can_insert": bool(parent),
        "can_delete": (node not in structural) and (bool(parent) or len(
            [slug for slug in by_slug if not parent_of(slug)]) > 1),
        "delete_expect": label or node,
        "destroys": doomed,
    }


def _writing_block(entry: Any, sandbox: str, node: str, log: Any) -> dict[str, Any]:
    """One writing as the CARD needs it: its text, and where a save or a delete goes.

    The routes are computed here, not chosen on the client, so a client that learned
    where a save goes could not learn it wrongly.

    A writing is a SLOT. It is saved by name (``save_note``, the slot's address) and
    deleted by deleting the slot — one verb, already gated, and already re-keying the
    slots after it. `save_node_note` remains the CREATE: a node with nothing on it yet
    has no slot to name.
    """
    del sandbox
    if not entry:
        return {"exists": False, "text": "", "name": "", "title": "", "kind": "",
                "confirm": "", "delete": None,
                "save": {"route": ROUTES["save_node_note"],
                         "fixed": {"node": node, "option": ""}}}
    name = _as_text(entry.get("name"))
    save = {"route": ROUTES["save_note"], "fixed": {"name": name}}
    delete = {"route": ROUTES["delete_node"],
              "fixed": {"node": name, "descendants": "delete"},
              "expect": _as_text(entry.get("confirm"))}
    del log
    return {
        "exists": True,
        "text": _as_text(entry.get("text")),
        "name": name,
        "title": _as_text(entry.get("title")),
        "kind": _as_text(entry.get("kind")),
        "confirm": _as_text(entry.get("confirm")),
        "save": save,
        "delete": delete,
    }


def _decorated(
    nodes: Any, writings: dict[str, Any], actions: dict[str, str], actions_root: str,
    log: Any = None, sandbox: str = "", anchor_name: str = "",
) -> list[dict[str, Any]]:
    """The tree nodes, each carrying what it SAYS as well as where it sits.

    This is what lets the picture answer "which nodes hold documents" before anything is
    clicked — the one thing the split pane could never show, because it learned a node's
    writing only after that node was selected.

    Under the log it answers a second question the shape alone cannot: WHICH document.
    A node carries the slot it denotes, and the slot carries the node that denotes it —
    both ends of one thread, so the picture can draw it at both ends and the operator can
    follow it in either direction.
    """
    meta = _as_text(getattr(log, "slot_root", ""))
    by_name = {_as_text(entry.get("name")): entry for entry in _every(writings)}
    holder = ({entry.slot: node for node, entry in log.entries.items() if entry.slot}
              if meta else {})
    out: list[dict[str, Any]] = []
    for entry in nodes or ():
        slug = _as_text(entry.get("full_slug"))
        parent = _as_text(entry.get("parent_slug"))
        is_slot = log is not None and log.is_document_node(slug)
        own = by_name.get(slug) if is_slot else writings["by_node"].get(slug)
        options = () if is_slot else writings["options"].get(slug, ())
        slot = _as_text(log.slot_of(slug)) if meta else _as_text(
            (own or {}).get("name") if own else "")
        out.append({
            **entry,
            "doc": ({"name": own["name"], "lines": own["lines"],
                     "preview": own["preview"], "confirm": own["confirm"],
                     "kind": own.get("kind", ""), "title": own.get("title", "")}
                    if own else None),
            "options": [{"option": o["option"], "preview": o["preview"],
                         "action": _domain.resolve_action(o["text"], actions)}
                        for o in options],
            "is_decision": bool(options),
            # An ACTION is a child of the actions root: a word the tree has agreed on, not
            # a subject. Marked so the surface can draw the vocabulary apart from the
            # policy that references it.
            "is_action": bool(actions_root) and parent == actions_root,
            # A SLOT is a document filed on the meta branch. Drawn apart from the domain
            # because it is a different KIND of thing — the ledger, not the policy.
            "is_slot": is_slot,
            "slot": slot if not is_slot else "",
            # Which node denotes THIS slot, so the ledger end of the thread reads as a
            # sentence rather than as an orphan.
            "denoted_by": holder.get(slug, "") if is_slot else "",
            # The GLYPH this node wears, as a slot on the icon branch. The face is sent
            # once at the top of the payload rather than per node: a hundred nodes wearing
            # the circle is one drawing, not a hundred.
            "icon": _as_text(log.icon_of(slug)) if log is not None else "",
            # Where the DOCUMENT is. Selecting a document node on the tree navigates to
            # it (operator, 2026-08-20) rather than opening a second inline reader: the
            # Compendium already has a level for an open document, with the raw datum
            # tab and the crumbs back out, and a second one here would be a third way
            # of looking at the same rows.
            "open": _document_href(sandbox, _document_id_of(
                _document_of(slug, is_slot, log, anchor_name), by_name))
            if (is_slot or slot) else "",
            "can_child": _as_text(entry.get("node_kind")) == NODE_KIND_TYPE and not own
            and not is_slot,
        })
    return out


def _document_id_of(name: str, by_name: dict[str, Any]) -> str:
    """The canonical id of the document called ``name``, or ``""``.

    Empty when the log names a document the sandbox does not hold — a slot can outlive its
    document, and a link to nothing is worse than no link.
    """
    entry = by_name.get(_as_text(name))
    return _as_text((entry or {}).get("document_id"))


def _document_of(slug: str, is_slot: bool, log: Any, anchor_name: str = "") -> str:
    """The document NAME a tree node addresses: its own slot, or the one it denotes.

    ``anchor_name`` because slot ``1-1`` names the sandbox's ANCHOR, which is called
    ``anchor`` or ``anthology`` depending on when the sandbox was made. Without it that
    one slot resolves to nothing and the anchor becomes the single document on the tree
    with no way to open it — measured on the migrated BPW tree before this was passed.
    """
    slot = slug if is_slot else _as_text(log.slot_of(slug) if log is not None else "")
    if not slot:
        return ""
    if log is None:
        return slot
    return _as_text(log.document_name_of_slot(slot, anchor_name=anchor_name))


def _document_href(sandbox: str, document_id: str) -> str:
    """The Compendium address of one document in one sandbox.

    Built here because the surface needs a real link and the client must not assemble
    one: a URL composed on the client is a second statement of the address grammar, and
    the level-honest-query rule (2026-08-16) is enforced on the server.

    The ``document`` param is the CANONICAL ID, never the short name. The workbench
    resolves it by matching ``document_rows``' ids, and a name that matches none of them
    is not an error there — it silently falls back to the sandbox's preferred document,
    which is the anchor. So a link built from a name opened the anchor for every document
    on the tree, and the page looked like it had worked.
    """
    if not document_id or not sandbox:
        return ""
    return (f"{WORKBENCH_UI_TOOL_ROUTE}?sandbox_filter={quote(sandbox)}"
            f"&document={quote(document_id)}")


class LclEditorViewer:
    """The lcl node graph beside whatever the selected node can be edited into."""

    tool_id = "lcl_editor"
    writes = (
        DeclaredWrite(document_kind="lcl_type", action="define_type"),
        DeclaredWrite(document_kind="lcl_type", action="delete_type"),
        DeclaredWrite(document_kind="lcl_type", action="define_record_type"),
        DeclaredWrite(document_kind="lcl_instance", action="create_instance"),
        DeclaredWrite(document_kind="lcl_instance", action="save_instance"),
        DeclaredWrite(document_kind="lcl_instance", action="delete_instance"),
        # The SAMRAS re-address verb (the name-first tree): a grouping node takes the
        # selection's address, the subtree re-keys, node notes follow. Non-destructive.
        DeclaredWrite(document_kind="lcl_type", action="insert_node"),
        # A SECOND top-level branch, beside `1`. Declared apart from `define_type`
        # because it is the one write here that changes the tree's shape at its widest
        # point, and an operator narrowing a grant should be able to allow growing an
        # existing branch while withholding starting a new one.
        DeclaredWrite(document_kind="lcl_type", action="define_root_type"),
        # The three restructuring verbs the domain card offers. Separately declared for
        # the same reason as above, and because they are not alike: a rename moves
        # nothing, a move re-keys two branches, and a delete destroys writings. An
        # operator narrowing a grant can allow tidying labels while withholding the verb
        # that can empty a branch.
        DeclaredWrite(document_kind="lcl_type", action="rename_node"),
        DeclaredWrite(document_kind="lcl_type", action="move_node"),
        DeclaredWrite(document_kind="lcl_type", action="delete_node"),
        # The document verbs. Separately declared because they are a different KIND of
        # write from the structural ones: creating a document adds a datum document to the
        # sandbox, attaching only changes which node denotes one, and an operator narrowing
        # a grant should be able to allow re-filing what exists while withholding creation.
        DeclaredWrite(document_kind="lcl_document", action="create_document"),
        DeclaredWrite(document_kind="lcl_document", action="attach_document"),
        DeclaredWrite(document_kind="lcl_document", action="detach_document"),
        # A FILE kept as a document and the slot that names it (2026-09-11): the artifact
        # twin of create_document, under the artifact branch's kind rather than the
        # documents branch. Declared here because the slot is a tree write whatever the
        # surface that posts it — Enchir's project page uploads through it, and the
        # route resolves the owner from the action, never from the poster.
        DeclaredWrite(document_kind="lcl_document", action="file_artifact"),
        # Its own declaration, and separately grantable for the same reason attach is: an
        # icon changes how a tree READS and never what it holds, so an operator narrowing
        # a grant can allow the polish and withhold the filing.
        DeclaredWrite(document_kind="lcl_document", action="set_node_icon"),
        # The WRITING verbs, owned here since `note_manager` retired with the name
        # convention (2026-08-20). An action has one owning tool and `_write_owners`
        # RAISES on a second declaration, so this is a move, not a copy.
        DeclaredWrite(document_kind="note", action="save_note"),
        DeclaredWrite(document_kind="note", action="save_node_note"),
    )
    label = "LCL Editor"
    # UI copy: the rail hover, one sentence from the user's side.
    summary = "Select a node in the graph to name types, add records, or write notes."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = SamrasStructureViewer.applies_to_archetype
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    # Launched by address (?tool=lcl_editor), opening on the active instance's own
    # structure — the instance switcher's answer, never a sandbox named in code.
    #: Every instance defines its own classification, so this is generic — but it needs a
    #: document to edit. An instance without an `lcl` has nothing for it to open.
    requires = ToolRequirement(
        documents=(
            DocumentRequirement(
                name=LCL_DOCUMENT, archetype="local_domain_log",
                why="the classification nodes this edits"),
        ),
    )
    # Demoted from the rail (calendar-only rail, 2026-08-16): the editor now opens
    # by OPENING a sandbox's `lcl` document in the Compendium, and stays composed
    # as Oveure's Domain tab. The capability moved into the document layer; the
    # tool stayed the one implementation of it.
    core = False

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None,
        sandbox_id: str,
        document_id: str,
        datum_address: str,
        extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        eq = extra_query or {}
        structure = _as_text(eq.get("samras_structure")) or _LCL_STRUCTURE
        tree = LocalDomainViewer().build_panel_payload(
            authority_db_file=authority_db_file,
            sandbox_id=sandbox_id,
            document_id=document_id,
            datum_address=datum_address,
            extra_query={"samras_structure": structure},
        )
        if tree.get("error"):
            return {**tree, "schema": _SCHEMA, "container": "domain_surface"}

        sandbox = _as_text(tree.get("sandbox_id")) or _as_text(sandbox_id)
        node = _as_text(eq.get(_SELECT_PARAM))

        # ONE read of everything this sandbox says — shared by the picture and the card.
        # Two readers of the writings would be two answers to "what does this instance
        # hold", and the operator would have no way to tell which one ran.
        writings, log, anchor_name = _writings(authority_db_file, sandbox)
        nodes = tree.get("nodes", ())
        actions_root = _domain.actions_root(nodes)
        actions = _domain.actions_index(nodes)

        payload: dict[str, Any] = {
            "schema": _SCHEMA,
            "container": "domain_surface",
            "sandbox_id": sandbox,
            "structure": _as_text(tree.get("structure")) or structure,
            "structures": tree.get("structures", []),
            "select_param": _SELECT_PARAM,
            "selected_node": node,
            "actions_root": actions_root,
            "actions": [{"node": address, "label": label}
                        for address, label in sorted(actions.items())],
            "nodes": _decorated(nodes, writings, actions, actions_root, log, sandbox,
                                anchor_name),
            "denoted_count": tree.get("denoted_count", 0),
            "defined_count": tree.get("defined_count", 0),
            "undenoted_nodes": tree.get("undenoted_nodes", []),
            "undenoted_reason": tree.get("undenoted_reason", ""),
            "routes": ROUTES,
            "limits": {"line_chars": _LINE_CHARS, "note_chars": _NOTE_CHAR_BUDGET,
                       "title_chars": _ld.TITLE_CHARS},
            # The document ledger, as data: where it lives, what kinds this surface can
            # create, and every slot with its title. The attach picker reads `slots` and
            # shows the TITLES, which is the operator's whole point about it — a picker
            # listing `1-7` beside `1-8` asks somebody to remember which is which.
            "log": _ledger(log, writings),
            # Every glyph this sandbox holds, decoded ONCE. The tree draws from it by slot
            # and the card's picker lists it by title, so "what glyphs are there" has one
            # answer on the screen instead of two that can disagree.
            "icons": _icon_faces(authority_db_file, sandbox, log),
            "empty_text": "No nodes denoted by the magnitude.",
        }
        if node:
            payload["card"] = _card(
                authority_db_file, sandbox, node, tree, writings, actions, log,
                anchor_name)
            panes = _record_panes(authority_db_file, sandbox, node, tree,
                                  noted=writings["by_node"])
            if panes:
                payload["panes"] = panes
        return payload


# Self-register on import.
register(LclEditorViewer())
