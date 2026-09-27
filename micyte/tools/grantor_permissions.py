"""The GRANTOR application's Permissions tab — what every connected port may do, and by whom.

The operator's ask, 2026-08-29: *"make sure that my instance, the FND instance, has its
working use of all FND service modules it uses to direct permissions from the Grantor
application."* Before this the Grantor could only REPORT — a rate card, a cost ledger — and
permitting an operation meant opening ``private/config.json`` in an editor. "Direct
permissions from the Grantor application" was not something the application could do.

## Three facts, and they are not one fact

Every row here says three things about one operation, because on the live host they
disagree:

* **DECLARED** — the running extension manifest implements it;
* **BOUND** — the binding's stored ``calls`` name it;
* **GRANTED** — an ``external_call_grants`` row permits it, for these actors.

MEASURED on the live FND config the day this was written: all eight ``*_site`` bindings are
GRANTED ``analytics.read``, ``content.replace`` and ``asset.upload`` — declared by nothing,
bound by nothing, and therefore permitting nothing. They read as configured. A pane showing
only "granted / not granted" would have shown twenty-four green cells for permissions that
do not exist, and a pane showing only the binding's declared calls would not have shown
them at all.

## Why the numbers come from the host

``micyte`` has no filesystem and no knowledge of this deployment's layout, so the matrix
ARRIVES through ``host_context``, computed by ``runtime/grant_matrix.build_grant_matrix`` —
the same function ``check_fnd_service_grants`` prints from. A tool in the published package
that reached for the host's config would be the crossing ``test_micyte_fnd_boundary``
exists to prevent, and a second derivation of "is this permitted" would be the drift
``build_analytics_summary`` was extracted to end.

## Connecting and permitting stay two acts

``port_binding_write_runtime`` keeps granting out of the Ports surface because "a form that
did both would make describing and permitting one gesture, and the gesture people make is
the permissive one". That still holds: Ports connects, and this — a different surface, in
the operator's own application — permits. What stopped being true is that the second act
required a text editor, which is not a review step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register
from .grantor_books import GRANTOR_SANDBOX

_SCHEMA = "mycite.v2.portal.workbench.tool.grantor_permissions.v1"

#: Which (binding, operation) the pane has open, as ``<binding_id>::<operation>``. Its OWN
#: query parameter, like every other drill-in here: sharing the parent hub's would move the
#: Grantor's tab as a side effect of opening a row.
TARGET_QUERY = "permission_target"

#: The separator. ``::`` because a binding id and an operation are both dotted/underscored
#: tokens (`fnd_site`, `article.publish`) and a single dot would split `article.publish`.
TARGET_SEP = "::"

#: Where the two verbs post. The route judges the caller; this only says which door.
_ROUTE = "/portal/api/v2/grantor"


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_target(raw: object) -> tuple[str, str]:
    """``"fnd_site::article.publish"`` -> ``("fnd_site", "article.publish")``.

    Split on the FIRST separator only. A binding id cannot contain ``::``; an operation
    could in principle, and losing its tail would silently address a different operation.
    """
    text = _as_text(raw)
    if TARGET_SEP not in text:
        return "", ""
    binding_id, _sep, operation = text.partition(TARGET_SEP)
    return _as_text(binding_id), _as_text(operation)


def _matrix(host_context: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    """``(matrix, why_not)`` — the host's answer, or the reason there is not one.

    The refusal is CARRIED rather than flattened into an empty table. "Nothing is
    connected" and "this render was handed no permissions reader" want opposite actions,
    and an empty table cannot tell them apart — the distinction ``pim_design`` draws for
    the site seam, for the same reason.
    """
    context = host_context if isinstance(host_context, dict) else {}
    provider = context.get("permissions")
    if not callable(provider):
        return {}, (
            "this portal did not offer a permissions reader to this render. The pane is "
            "the operator's own — a sign-in that is not the operator is not shown what "
            "the host holds for every alias.")
    try:
        matrix = provider()
    except Exception as exc:  # the host's own refusal, in the host's own words
        return {}, str(exc)
    if not isinstance(matrix, dict):
        return {}, "the permissions reader answered with something that is not a matrix"
    return matrix, ""


def _cell(values: Any) -> str:
    items = [_as_text(v) for v in (values or ()) if _as_text(v)]
    return ", ".join(items) if items else "—"


def _state_word(state: dict[str, Any]) -> str:
    """The DECLARED column, in words rather than a tick.

    "no" is not the useful answer for an operation the manifest does not implement while a
    grant for it sits on file. The word says which of the two situations a row is in, so a
    reader does not have to cross-reference the granted column to find out.
    """
    if state.get("declared"):
        return "yes"
    return "NO — nothing implements it" if state.get("granted") else "no"


def _notice(title: str, text: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "record_table", "title": title,
            "columns": ["note"], "rows": [], "row_count": 0, "empty_text": text}


_COLUMNS = ["connection", "instance", "port", "extension", "operation",
            "declared", "bound", "granted", "refused"]


def _overview(matrix: dict[str, Any]) -> dict[str, Any]:
    """Every (binding, operation) on this host, one row each.

    Flat rather than nested, and one `pick` rather than two: the question an operator
    arrives with is about an operation on a connection, and making them choose the
    connection first would be a level of navigation that answers nothing on its own.
    """
    rows: list[dict[str, Any]] = []
    options: list[dict[str, str]] = []
    undeclared = 0
    for binding in matrix.get("bindings") or ():
        for state in binding.get("operations") or ():
            if not state.get("declared"):
                undeclared += 1
            rows.append({
                "connection": binding["label"],
                "instance": binding["msn_id"],
                "port": binding["port_id"],
                "extension": binding["extension_label"],
                "operation": state["operation"],
                "declared": _state_word(state),
                "bound": "yes" if state.get("bound") else "no",
                "granted": _cell(state.get("granted")),
                "refused": _cell(state.get("refused")),
                # Drawn differently: a granted operation nothing implements is the row an
                # operator is here to find.
                "is_flagged": bool(state.get("granted")) and not state.get("declared"),
            })
            options.append({
                "value": f"{binding['binding_id']}{TARGET_SEP}{state['operation']}",
                "label": f"{binding['label']} — {state['operation']}",
            })
    refused_bindings = matrix.get("refused") or []
    notice = (
        f"{len(rows)} operation(s) across "
        f"{len(matrix.get('bindings') or ())} connection(s). "
        "DECLARED is what the running extension manifest implements, BOUND is what the "
        "connection stores, GRANTED is who may actually call it."
    )
    if undeclared:
        notice = (
            f"{notice} {undeclared} operation(s) are granted or bound without the manifest "
            "implementing them — a permission for nothing, and invisible to the auditor.")
    if refused_bindings:
        notice = (
            f"{notice} {len(refused_bindings)} binding(s) in this config could not be "
            f"read: {'; '.join(f'{b[0]}: {b[1]}' for b in refused_bindings)}.")
    return {
        "schema": _SCHEMA, "container": "record_table", "title": "Permissions",
        "columns": _COLUMNS, "rows": rows, "row_count": len(rows),
        "row_class_key": "is_flagged",
        "count_label": f"{len(rows)} operation{'' if len(rows) == 1 else 's'}",
        "empty_text": (
            "No port is connected on this host. Select an extension for a port on "
            "Utilities > Ports first — there is nothing to permit until something is "
            "standing in a seam."),
        "notice": notice,
        "pick": {"label": "Manage", "param": TARGET_QUERY,
                 "options": options, "go_label": "Open"} if options else None,
    }


def _actor_options(binding: dict[str, Any]) -> list[dict[str, str]]:
    """The actors of this connection, DEDUPED by actor id.

    ``callers_for`` names four callers and two of them can be one actor: on FND's own
    bindings the "client dashboard" and the "operator console" are both
    ``grantee:<FND's msn>``, because FND is its own client there. Two options carrying one
    value would let an operator believe they had granted two different things.
    """
    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for actor in binding.get("actors") or ():
        actor_id = _as_text(actor.get("actor_id"))
        if not actor_id or actor_id in seen:
            continue
        seen.add(actor_id)
        label = _as_text(actor.get("label"))
        options.append({
            "value": actor_id,
            "label": f"{label} — {actor_id}" if label and label != actor_id else actor_id,
        })
    return options


def _target_pane(matrix: dict[str, Any], binding_id: str, operation: str,
                 *, sandbox: str) -> dict[str, Any]:
    """One operation on one connection: who holds it, and the two verbs."""
    binding = next((b for b in (matrix.get("bindings") or ())
                    if b["binding_id"] == binding_id), None)
    if binding is None:
        overview = _overview(matrix)
        overview["notice"] = (
            f"No connection called {binding_id!r} is readable here any more — it may have "
            "been unbound. Here is what this host carries now.")
        return overview
    state = next((s for s in (binding.get("operations") or ())
                  if s["operation"] == operation), None)
    if state is None:
        overview = _overview(matrix)
        overview["notice"] = (
            f"{binding['label']} no longer names {operation!r} — the manifest, the binding "
            "or the grant that mentioned it is gone. Here is what this host carries now.")
        return overview

    granted = set(state.get("granted") or ())
    actor_rows = [
        {"actor": actor["actor_id"], "who": actor["label"],
         "may call it": "yes" if actor["label"] in granted else "no"}
        for actor in _dedupe_actor_rows(binding)
    ]
    declared = bool(state.get("declared"))
    facts = {
        "schema": _SCHEMA, "container": "record_table",
        "title": f"{binding['label']} — {operation}",
        "columns": ["actor", "who", "may call it"],
        "rows": actor_rows, "row_count": len(actor_rows),
        "count_label": f"{len(granted)} of {len(actor_rows)} permitted",
        "empty_text": "This connection has no callers.",
        "notice": (
            f"{binding['port_id']} filled by {binding['extension_label']} for instance "
            f"{binding['msn_id']} (sandbox {', '.join(binding['sandbox_ids'])}). "
            f"Declared by the manifest: {'yes' if declared else 'NO'}. "
            f"Bound on the connection: {'yes' if state.get('bound') else 'no'}. "
            f"Employed by: {_cell(state.get('employed_by'))}."
            + (f" {state['why']}" if state.get("why") else "")),
        # Clearing the parameter IS the return, the same way every drill-in here comes back.
        "back": {"label": "All permissions", "param": TARGET_QUERY, "value": ""},
    }

    actors = _actor_options(binding)
    if declared:
        grant: dict[str, Any] = {
            "schema": _SCHEMA, "container": "record_form",
            "title": f"Permit {operation}",
            "fields": [{
                "key": "actor_id", "label": "Who may call it", "type": "select",
                "value": actors[0]["value"] if actors else "", "options": actors,
            }],
            "submit_label": "Grant",
            "submit_action": {
                "route": f"{_ROUTE}/grant", "sandbox_id": sandbox,
                "success_label": "Granted",
                # The operation and the connection are FIXED, never fields. A form that let
                # an operator type either would let them name one the manifest does not
                # implement, and the route would refuse — a control that offers what the
                # server rejects teaches nothing.
                "fixed": {"binding_id": binding_id, "operation": operation},
            },
        }
    else:
        grant = _notice(
            f"Cannot permit {operation}",
            f"The running {binding['extension_label']} manifest does not implement "
            f"{operation!r} on {binding['port_id']}, so a grant for it would permit "
            "nothing. If a grant is already on file below, withdraw it — that is the state "
            "a hand-edited config leaves behind when a manifest changes.")

    revoke = {
        "schema": _SCHEMA, "container": "record_form",
        "title": f"Withdraw {operation}",
        "fields": [{
            "key": "actor_id", "label": "From whom", "type": "select",
            "value": actors[0]["value"] if actors else "", "options": actors,
        }],
        "submit_label": "Revoke",
        "submit_action": {
            "route": f"{_ROUTE}/revoke", "sandbox_id": sandbox, "danger": True,
            "success_label": "Withdrawn",
            "fixed": {"binding_id": binding_id, "operation": operation},
            # The SHARED typed dialog, and the operation's own name as the word. A revoke
            # breaks a working integration silently — the tab that used it stops answering
            # and nothing about the failure says a permission was withdrawn — so it is
            # asked for the way a delete is, and the server checks the same text.
            "confirm": {
                "expect": operation, "key": "confirm",
                "text": (
                    f"This withdraws {operation!r} on {binding['label']} from the actor "
                    "selected above. Whatever was using it starts refusing, and the "
                    "refusal will not say that a permission was removed. Granting it back "
                    "is one press."),
            },
        },
    }
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": facts}, {"panel_payload": grant},
                      {"panel_payload": revoke}]}


def _dedupe_actor_rows(binding: dict[str, Any]) -> list[dict[str, str]]:
    """The actor list with duplicate ids collapsed, keeping the FIRST label.

    Same reason as ``_actor_options``, and separate from it because the table shows the
    label a caller is known by while the form needs the value that is sent.
    """
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for actor in binding.get("actors") or ():
        actor_id = _as_text(actor.get("actor_id"))
        if not actor_id or actor_id in seen:
            continue
        seen.add(actor_id)
        out.append({"actor_id": actor_id, "label": _as_text(actor.get("label")) or actor_id})
    return out


class GrantorPermissions:
    """Who may call what, through which connection — and the two verbs that change it."""

    tool_id = "grantor_permissions"
    label = "Permissions"
    summary = (
        "Every port connected on this host, and per operation whether the manifest "
        "declares it, the connection binds it, and a grant permits it — with grant and "
        "revoke on the same screen. FND only: this is the operator's side."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    #: A hub tab launched by ADDRESS, like the two it sits beside.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    #: The facts live in this instance's config, which `micyte` may not read for itself.
    wants_host_context = True
    #: Which row is open. See `TARGET_QUERY`.
    wants_surface_query = True

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None = None,
        sandbox_id: str = "",
        document_id: str = "",
        datum_address: str = "",
        host_context: dict[str, Any] | None = None,
        extra_query: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        del authority_db_file, document_id, datum_address
        matrix, why_not = _matrix(host_context)
        if why_not:
            return _notice(self.label, why_not)
        sandbox = _as_text(sandbox_id) or GRANTOR_SANDBOX
        query = extra_query if isinstance(extra_query, dict) else {}
        binding_id, operation = parse_target(query.get(TARGET_QUERY))
        if binding_id and operation:
            return _target_pane(matrix, binding_id, operation, sandbox=sandbox)
        return _overview(matrix)


register(GrantorPermissions())
