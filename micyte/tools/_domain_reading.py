"""What a local domain SAYS — its documents, its decisions and its actions, read once.

The lcl tree is a shape; this is the meaning hung on it. Three surfaces need the same
answer and must not each work it out: the Domain surface draws it, the card edits it, and
``email_triage_runtime`` sends it to a model as the instance's policy. Two readers of one
fact are two facts (the ``ledger_books`` rule), so there is one function per question and
every consumer calls it.

## One convention

A node's definition row names the SLOT it denotes, and the document is called that slot.
The older convention — the association in the document's NAME (``note_2-1-3``,
``note_2-1-3_yes``) — was live for one day and is gone: the 2026-08-20 migration left zero
documents named that way on the corpus, and a fallback nothing can reach is a second
answer to "what does this instance hold" that nobody would notice going wrong.

Three conventions of meaning, unchanged by the move:

the node's own writing
    the document a node denotes.

an ANSWER
    a document whose TITLE is ``<node> <option>`` (``2-1-3 yes``). An answer is a document
    because a node holding a writing takes no children (the leaf rule), so a decision that
    posed its question on the node could not own ``yes``/``no`` nodes. Under the log the
    convention lives in the title cell rather than in a filename, which is the whole point
    of the change — but it is the operator's own naming either way.

a REFERENCE
    a writing whose whole text is a node address. Where the tree carries a root labelled
    ``actions``, that is how a branch says what to do without anybody parsing prose for a
    verb — an address can be checked against the tree and a word cannot, which is the same
    reason a triage decision is an address.

A node is a DECISION because it has answers. Nothing declares it, so nothing can declare it
wrongly.
"""

from __future__ import annotations

import re
from typing import Any

from micyte.core.datum_ops import local_domain as _ld
from micyte.core.datum_ops.datum_resolve import as_text

#: The label a root must carry for its children to be actions. A label, not an address:
#: the operator names the branch, and `insert_node` can re-key it to any number.
ACTIONS_LABEL = "actions"

#: A writing that is nothing but an address. Anchored and whole-string: a note whose first
#: line MENTIONS 3-1 in a sentence is prose, and reading it as a reference is exactly the
#: mistake `action_for`'s prose scanner made before it was rewritten.
_ADDRESS_ONLY = re.compile(r"^[0-9]+(?:-[0-9]+)*$")

#: How much of a writing rides in the tree picture. One stored line is 64 characters, and
#: a chip wider than that stops being a chip.
PREVIEW_CHARS = 64

#: A document read for the shelf is skipped over this budget rather than loaded — the
#: registrar sandbox holds a 27 MB address table, and a shelf that read it to count lines
#: would cost 27 MB to say "not a writing".
_LIST_PAYLOAD_BUDGET = 2_000_000


def preview_of(text: str) -> str:
    """A writing's first line, clipped — what a node chip shows without being opened."""
    first = next((line.strip() for line in as_text(text).splitlines() if line.strip()), "")
    return first if len(first) <= PREVIEW_CHARS else first[: PREVIEW_CHARS - 1].rstrip() + "…"


def action_reference(text: str) -> str:
    """The node address a writing IS, or ``""`` when it is prose.

    The whole writing, not its first line: "3-1" followed by a paragraph explaining why is
    prose with an address at the top, and treating it as a reference would silently ignore
    the paragraph. A reference is a writing that says one thing.
    """
    body = as_text(text).strip()
    return body if _ADDRESS_ONLY.match(body) else ""


def _address(entry: Any) -> str:
    """A node's address, whichever of the two shapes it arrived in.

    The tree payload calls it ``full_slug`` (the viewer's key) and the triage reader calls
    it ``node``. Both are the same fact and both ask this module the same questions, so the
    normalisation lives here rather than as a second copy of `actions_index` per shape.
    """
    return as_text(entry.get("full_slug") or entry.get("node"))


def _parent(entry: Any) -> str:
    return as_text(entry.get("parent_slug") or entry.get("parent"))


def actions_root(nodes: Any) -> str:
    """The address of the root labelled ``actions``, or ``""``.

    Only a ROOT counts. A node called "actions" three levels down inside a services branch
    is a subject, not a vocabulary, and promoting it to one would let an unrelated tree
    start resolving addresses through it.
    """
    for node in nodes or ():
        entry = node if isinstance(node, dict) else {}
        if _parent(entry):
            continue
        if as_text(entry.get("label")).strip().lower() == ACTIONS_LABEL:
            return _address(entry)
    return ""


def actions_index(nodes: Any) -> dict[str, str]:
    """``{address: label}`` for the children of the actions root — the vocabulary, as data.

    Direct children only. The action is the WORD an operator chose (`ignore`, `forward`),
    and a grandchild would be a qualification of one, which nothing here knows how to act
    on.
    """
    root = actions_root(nodes)
    if not root:
        return {}
    out: dict[str, str] = {}
    for node in nodes or ():
        entry = node if isinstance(node, dict) else {}
        if _parent(entry) == root:
            out[_address(entry)] = as_text(entry.get("label"))
    return out


def resolve_action(text: str, actions: dict[str, str]) -> dict[str, str] | None:
    """``{"node", "label"}`` for a writing that references an action, else ``None``.

    An address the vocabulary does not hold returns ``None`` with its own address kept, so
    a surface can show "names 3-9, which is not an action" rather than quietly resolving
    to nothing. That distinction is the caller's to draw; this answers only "is it one".
    """
    address = action_reference(text)
    if not address:
        return None
    label = actions.get(address)
    if label is None:
        return None
    return {"node": address, "label": label}


def _entry(
    *, name: str, node: str, option: str, title: str, text: str, kind: str,
    document_id: str, confirm: str,
) -> dict[str, Any]:
    """One writing, in the shape every consumer of this module already speaks."""
    return {
        "name": name,
        "node": node,
        "option": option,
        "title": title,
        "kind": kind,
        "text": text,
        "lines": 0 if not text else text.count("\n") + 1,
        "preview": preview_of(text),
        "display": title or name,
        # What a delete will ask to have typed back. Carried rather than derived on the
        # client: the server owns the confirmation text, and a dialog that asks for
        # something the gate does not expect is a dialog nobody can get past.
        "confirm": confirm,
        "document_id": document_id,
    }


def _by_name(store: Any, *, tenant_id: str, sandbox: str, msn_id: str = "") -> dict[str, Any]:
    """``{document name: document}`` for one sandbox — the single read this module makes."""
    from micyte.core.document_naming import parse_canonical_document_id

    out: dict[str, Any] = {}
    kwargs: dict[str, Any] = {"tenant_id": tenant_id, "sandbox": sandbox,
                              "max_payload_bytes": _LIST_PAYLOAD_BUDGET}
    if msn_id:
        kwargs["msn_id"] = msn_id
    for document in store.read_documents_by_sandbox(**kwargs):
        try:
            out[parse_canonical_document_id(as_text(document.document_id)).name] = document
        except Exception:
            continue
    return out


def _text_of(document: Any, *, sandbox: str, registry: Any) -> tuple[str, str]:
    """``(text, archetype)`` — the writing a document holds, and what kind it is.

    Only a ``text_note`` has text. A contacts sheet or an event log is a real document with
    a real shape, and rendering its rows as a "writing" would be this surface claiming to
    read a document that belongs to another tool.
    """
    from .note_books import NOTE_ARCHETYPE, note_text

    kind = as_text((getattr(document, "document_metadata", None) or {}).get("archetype"))
    if kind and kind != NOTE_ARCHETYPE:
        return "", kind
    archetype = registry.get(NOTE_ARCHETYPE) if registry is not None else None
    return note_text(document, sandbox=sandbox, archetype=archetype), kind or NOTE_ARCHETYPE


def read_writings(
    store: Any, *, tenant_id: str, sandbox: str, registry: Any, log: Any = None,
    msn_id: str = "",
) -> dict[str, Any]:
    """Every writing in one sandbox, sorted onto the tree.

    ``{"by_node": {node: entry}, "options": {node: [entry, ...]}, "unassigned": [entry, ...]}``

    One pass over the sandbox's documents — so the gallery, the tree picture and the triage
    prompt cannot disagree about what this instance says.
    """
    documents = _by_name(store, tenant_id=tenant_id, sandbox=sandbox, msn_id=msn_id)
    by_node: dict[str, dict[str, Any]] = {}
    options: dict[str, list[dict[str, Any]]] = {}
    unassigned: list[dict[str, Any]] = []

    if log is None or not getattr(log, "meta_root", ""):
        # A sandbox with no documents branch files no documents, so it says nothing. Not
        # an error and not a fallback: the tree is where a writing lives now, and a tree
        # with no branch has none.
        return {"by_node": {}, "options": {}, "unassigned": []}
    for slot, slot_entry in log.slots().items():
        if log.is_reserved(slot):
            # The anchor and the log itself. Both are documents and neither is a WRITING
            # about a node — listing them here would put the sandbox's ground truth on a
            # node chip as if somebody had written it there.
            continue
        document = documents.get(slot)
        if document is None:
            # A slot whose document is missing is a defect worth SHOWING rather than
            # hiding: the tree says a document is there and the store disagrees, and
            # an operator can only fix what they can see.
            text, kind = "", ""
        else:
            text, kind = _text_of(document, sandbox=sandbox, registry=registry)
        title = slot_entry.label
        answered, option = _ld.parse_slot_title(title)
        entry = _entry(
            name=slot, node=answered or log.node_of_slot(slot), option=option,
            title=title, text=text, kind=kind, confirm=title,
            document_id=as_text(getattr(document, "document_id", "")),
        )
        if option:
            options.setdefault(answered, []).append(entry)
        elif entry["node"]:
            by_node[entry["node"]] = entry
        else:
            unassigned.append(entry)

    for entries in options.values():
        entries.sort(key=lambda e: e["option"])
    unassigned.sort(key=lambda e: e["display"])
    return {"by_node": by_node, "options": options, "unassigned": unassigned}


__all__ = [
    "ACTIONS_LABEL",
    "PREVIEW_CHARS",
    "action_reference",
    "actions_index",
    "actions_root",
    "preview_of",
    "read_writings",
    "resolve_action",
]
