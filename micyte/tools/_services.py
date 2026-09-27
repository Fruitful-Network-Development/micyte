"""The SERVICES a sandbox offers — the tree's own `services` branch as a selection.

Operator, 2026-09-17: the contact form should also start a job, *"giving them a more
intuitive and coherent [form-field] selection of jobs needed which I would like to be
informed by the jobs and job types defined and configured in the local domain."*

The vocabulary already exists and is already the operator's: on a pressure-washing
instance's tree it is
``objects/services/trade/pressure_washing/{house_wash, driveway, patio, …}``,
``…/gutter_cleaning``, ``…/general_handyman/{vehicle_service, …}`` — minted in the Domain
editor, no code. What did NOT exist was one reading of it. `job_manager._lcl_options`
offered EVERY operator node as a trade — measured on 2026-09-10 as "28 trades and kinds
offered", `outcomes/no_answer` and `kind/legal` among them — and the several-services form
asked for services as typed lines. Two surfaces, two readings, neither the tree's.

This is the one reading. It knows the tree and nothing about any surface:

* :func:`service_options` — every node under the branch labelled ``services`` (found BY
  LABEL, the way every branch on a canonical tree is) that is a job someone could ask
  for: the `trade` layer is skipped as structure, and each option carries its TRADE as a
  group and its depth under the trade, so a form can draw *Pressure washing > House wash
  > 2 story* and a customer can pick "House wash" without having to know the tree. Tree
  order, not alphabetical — the order the operator arranged is the order they meant.
* :func:`services_from_selection` — a posted selection back into the ``services`` a job
  document takes, refusing anything the branch does not offer. What a form posts is
  judged against what it was offered, so a stale page cannot file a job for a trade
  since deleted.
* :func:`no_services_branch` — the sentence for a tree that has not grown one, which is
  where the answer is (the Domain editor) rather than "no options".

Without a ``services`` branch the older rule stands — every operator node — so the seven
instances whose trees predate the branch keep working exactly as they did. That is the
canvassing writer's precedent for its `outcomes` branch, applied one branch over.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text
from micyte.core.datum_ops.node_addrs import parent_of

from ._place import humanise

#: The branch the operator grows trades under, and the one layer of structure beneath it.
SERVICES_LABEL = "services"
TRADE_LAYER_LABELS: frozenset[str] = frozenset({"trade", "trades"})


def _label(log: Any, node: str) -> str:
    return as_text(log.label_of(node)).strip()


def services_root(log: Any) -> str:
    """The node labelled ``services`` under the operator's objects, or ``""``."""
    object_root = as_text(getattr(log, "object_root", "")) or ""
    candidates = [node for node, entry in (getattr(log, "entries", None) or {}).items()
                  if as_text(entry.label).strip().lower() == SERVICES_LABEL]
    if object_root:
        under = [n for n in candidates if parent_of(n) == object_root]
        if under:
            return under[0]
    return candidates[0] if candidates else ""


def service_options(log: Any) -> list[dict[str, Any]]:
    """``[{value, label, group, depth, path}]`` — every job a customer could ask for, in
    tree order. Empty when the tree has no ``services`` branch.

    ``label`` is the node's own name said out loud (``house_wash_2_story`` →
    *House wash 2 story*), ``group`` is the trade it belongs to, ``depth`` is how far
    under the trade it sits (0 = the trade itself), and ``path`` is the whole line for a
    surface that wants it. A trade with children is offered too — a customer may want
    "pressure washing" without yet knowing which — and its children beneath it.
    """
    root = services_root(log)
    if not root:
        return []
    out: list[dict[str, Any]] = []

    def walk(node: str, *, group: str, depth: int, path: list[str]) -> None:
        for child in log.children_of(node):
            label = _label(log, child)
            if not label or log.is_document_node(child):
                continue
            if label.lower() in TRADE_LAYER_LABELS and depth == 0 and not group:
                # The `trade` layer is structure: what it holds are the trades.
                walk(child, group=group, depth=depth, path=path)
                continue
            said = humanise(label)
            here = [*path, said]
            trade = group or said
            out.append({"value": child, "label": said, "group": trade,
                        "depth": depth, "path": " > ".join(here)})
            walk(child, group=trade, depth=depth + 1, path=here)

    walk(root, group="", depth=0, path=[])
    return out


def services_from_selection(
    selected: Any, options: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """``(services, refusal)`` — a posted selection as the ``services`` a job document
    takes, or the sentence saying what was not offered.

    Accepts a list or a comma/newline-separated string of node addresses. Order is the
    tree's, not the click order, and a node picked twice is one service.
    """
    if isinstance(selected, str):
        tokens = [t.strip() for t in selected.replace("\n", ",").split(",")]
    elif isinstance(selected, (list, tuple)):
        tokens = [as_text(t).strip() for t in selected]
    else:
        tokens = []
    wanted = {t for t in tokens if t}
    if not wanted:
        return [], ""
    offered = {as_text(o.get("value")): o for o in options}
    unknown = sorted(wanted - set(offered))
    if unknown:
        return [], (f"not among the services this instance offers: {', '.join(unknown)} — "
                    "the list is the tree's own `services` branch")
    return [{"lcl_id": as_text(o["value"])} for o in options
            if as_text(o.get("value")) in wanted], ""


def no_services_branch(sandbox: str) -> str:
    """The empty state for a tree with no ``services`` branch, written for whoever reads it."""
    return (f"{sandbox} has no `services` branch on its domain tree yet, so there is nothing "
            "to choose from. Add one in the Domain editor — a `services` node with a trade "
            "under it, and the jobs under that — and it appears here with no code at all.")


def offered_services(
    store: Any, *, tenant_id: str, sandbox: str, msn_id: str = "",
) -> tuple[list[dict[str, Any]], Any]:
    """``(options, log)`` for one sandbox's tree — ONE read of the local domain.

    Both surfaces and the write route call this, so what a form was offered and what the
    route accepts come off the same document. ``msn_id`` names WHOSE sandbox: every
    instance keeps one called `system`, and the lookup refuses to guess between them.
    """
    from micyte.core.datum_ops import local_domain as ld

    from ._viewscope import local_domain_document_id, read_document

    lcl_id = local_domain_document_id(
        store, tenant_id=tenant_id, sandbox=sandbox, msn_id=msn_id)
    log = ld.read_log(read_document(store, tenant_id=tenant_id, document_id=lcl_id)
                      if lcl_id else None)
    return service_options(log), log


def pick_field(
    options: list[dict[str, Any]], *, key: str = "services", label: str = "Jobs needed",
    value: list[str] | None = None,
) -> dict[str, Any]:
    """The `record_form` field both surfaces draw the selection with — ONE shape.

    A `checkboxes` field: the renderer draws one fieldset per ``group`` (the trade) and
    indents by ``depth``, and posts the checked values as a list under ``key``. Declared
    here rather than in each surface so the contact form and the job form cannot offer
    the same tree two different ways.
    """
    return {
        "key": key, "type": "checkboxes", "label": label, "value": list(value or []),
        "options": [{"value": o["value"], "label": o["label"], "group": o["group"],
                     "depth": o["depth"]} for o in options],
    }


def labels_for(services: list[dict[str, Any]], options: list[dict[str, Any]]) -> list[str]:
    """The offered labels for a list of ``{lcl_id}`` services, in the tree's order."""
    wanted = {as_text(s.get("lcl_id")) for s in services}
    return [as_text(o.get("label")) for o in options if as_text(o.get("value")) in wanted]


__all__ = ["SERVICES_LABEL", "TRADE_LAYER_LABELS", "labels_for", "no_services_branch",
           "offered_services", "pick_field", "service_options", "services_from_selection",
           "services_root"]
