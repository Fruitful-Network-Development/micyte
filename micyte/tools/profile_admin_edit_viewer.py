"""``profile_admin_edit`` — browse any registry node, then curate its entries and events.

What it is for
--------------
The registry knows 235 nodes and holds very little about most of them. 121 of the 123 farm
legal entities have no instance of their own, so the registrar is their directory, and until now
nothing could edit that directory except the map-shaped MSN Node Manager — which only sees the
177 nodes that publish an ag profile, and only edits the ag profile itself.

This browses the **card directory**, so a township with no farm stand is still findable, and it
edits two things the operator named: the scalar **entries** on a profile row, and the **events**
that say when a farm is actually open (109 of 123 farms have none recorded).

How it relates to the Network Browser
-------------------------------------
Same model — :mod:`micyte.domains.registry.directory`. The Browser is the read surface and stays
read-only; this is the write surface. Sharing ``build_directory_model`` / ``build_profile`` means
the operator edits exactly what the Browser shows, including sections from documents neither
module names, because a profile is assembled by scanning the sandbox rather than from a list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.structures.hops import decode_hops_coordinate_token
from micyte.domains.registry import directory as _dir
from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import read_sandbox_catalog
from ._registry import register
from ._requirements import REGISTRAR
from ._shared.utilities import as_text as _as_text
from .network_map_viewer import iter_event_log_entries

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.profile_admin_edit.v1"
TOOL_ID = "profile_admin_edit"

NODE_PARAM = "profile_node"
REGION_PARAM = "profile_region"
QUERY_PARAM = "profile_q"

SAVE_ENTRY_ROUTE = "/portal/api/v2/registrar/save_profile_entry"
CREATE_EVENT_ROUTE = "/portal/api/v2/registrar/create_event"
SAVE_EVENT_ROUTE = "/portal/api/v2/registrar/save_event"
DELETE_EVENT_ROUTE = "/portal/api/v2/registrar/delete_event"

#: How many nodes an unfiltered browse lists. The directory is 235 nodes; showing all of them
#: with no filter makes the search box look broken. The payload always reports the true total
#: beside the shown count so a truncation is never mistaken for an empty registry.
_BROWSE_LIMIT = 60

#: Event classes offered when creating. Sourced from the lcl at render time; this is the order
#: they are presented in, not the vocabulary.
_CLASS_ORDER = ("1-3-3", "1-3-1", "1-3-2", "1-3-4", "1-3-5", "1-3-6")

_KIND_LABELS = {"1-3-8-1": "Open hours", "1-3-8-2": "Off season", "1-3-8-3": "Holiday"}
_UNIT_LABELS = {"1-6-1": "days", "1-6-2": "hours", "1-6-3": "minutes"}
_STRUCTURE_LABELS = {
    "1-5-3": "Weekly (hebdomadal) — stamp is <weekday>-<hour>-<minute>, span in minutes",
    "1-5-2": "Seasonal (quadrennium) — stamp is a day of the cycle, span in days",
}

#: Which documents' rows carry editable fields, and what to call each field in the form. Kept in
#: step with ``registrar_write_runtime.EDITABLE`` by a test rather than by hope: a field offered
#: here that the runtime refuses is a form that silently does nothing.
#:
#: ``farm_profile`` was removed here on 2026-08-22, in step with its retirement from
#: ``registrar_write_runtime.EDITABLE``. The form had been offering six fields the runtime
#: could not write — the document left this sandbox in Phase 3b — which is the exact failure
#: the note above names: "a field offered here that the runtime refuses is a form that
#: silently does nothing". Farm sections still RENDER, because ``_editable_rows`` returns
#: sections with no declared fields; they are read-only until the agnet anchor declares
#: writable field babelettes.
EDITABLE_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "legal_entity": (("dns", "DNS"),),
    "registry": (("dns", "DNS"), ("email", "Email"), ("website", "Website")),
}


def _notice(message: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "tool_id": TOOL_ID, "mode": "browse", "notice": message}


# --------------------------------------------------------------------------- #
# Browse
# --------------------------------------------------------------------------- #
def _matches(node: _dir.Node, needle: str) -> bool:
    if not needle:
        return True
    haystack = " ".join([node.title, node.msn_id, node.dns, node.website,
                         node.region_label, node.county_label, *node.ag_profiles]).lower()
    return needle in haystack


def build_browse_payload(model: _dir.RegistryDirectoryModel, *, region: str = "",
                         needle: str = "") -> dict[str, Any]:
    needle = needle.strip().lower()
    selected = [n for n in model.nodes
                if (not region or n.region_node == region or n.county_node == region)
                and _matches(n, needle)]
    selected.sort(key=lambda n: (n.title.lower(), n.msn_id))
    return {
        "schema": _SCHEMA,
        "tool_id": TOOL_ID,
        "mode": "browse",
        "node_param": NODE_PARAM,
        "region_param": REGION_PARAM,
        "query_param": QUERY_PARAM,
        "selected_region": region,
        "query": needle,
        "total_nodes": len(model.nodes),
        "match_count": len(selected),
        "shown_count": min(len(selected), _BROWSE_LIMIT),
        "regions": [
            {"node": r.node, "label": r.label, "depth": r.depth,
             "jurisdiction_type": r.jurisdiction_type, "node_count": r.node_count}
            for r in model.regions if r.node_count
        ],
        "nodes": [
            {"msn_id": n.msn_id, "title": n.title, "entity_kind": n.entity_kind,
             "entity_kind_label": n.entity_kind_label, "region_label": n.region_label,
             "county_label": n.county_label, "dns": n.dns,
             "ag_profiles": list(n.ag_profiles)}
            for n in selected[:_BROWSE_LIMIT]
        ],
        "missing_documents": list(model.missing_documents),
    }


# --------------------------------------------------------------------------- #
# Detail
# --------------------------------------------------------------------------- #
def _events_for(documents: dict[str, Any], msn_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in ("qc_log", "hc_log", "lc_log"):
        document = documents.get(name)
        if document is None:
            continue
        for entry in iter_event_log_entries(document):
            if entry.get("node") != msn_id:
                continue
            out.append({
                "log": name,
                "datum_address": entry.get("datum_address", ""),
                "label": entry.get("label", ""),
                "title": entry.get("title", ""),
                "event_class": entry.get("event_class", ""),
                "event_kind": entry.get("event_kind", ""),
                "event_kind_label": _KIND_LABELS.get(str(entry.get("event_kind")), ""),
                "structure": entry.get("structure", ""),
                "stamps": list(entry.get("stamps") or []),
                "span": entry.get("span", 0),
                "span_unit": entry.get("span_unit", ""),
                "span_unit_label": _UNIT_LABELS.get(str(entry.get("span_unit")), ""),
            })
    return out


def _editable_rows(profile: _dir.Profile) -> list[dict[str, Any]]:
    """The profile's sections, annotated with which fields a form may set.

    Sections from documents with no declared editable fields are still returned — they are what
    the node actually holds, and hiding them would make the editor a different view of the data
    than the Browser shows.
    """
    out: list[dict[str, Any]] = []
    for section in profile.sections:
        fields = EDITABLE_FIELDS.get(section.document, ())
        for row in section.rows:
            held = {f["field"]: f["value"] for f in row["fields"]}
            out.append({
                "document": section.document,
                "datum_address": row["datum_address"],
                "label": row["label"],
                "fields": row["fields"],
                "editable": [
                    {"field": key, "label": label,
                     "value": held.get(_RUNTIME_FIELD_SOURCE.get(key, key), "")}
                    for key, label in fields
                ],
            })
    return out


#: A form field's name is the runtime's, but the value shown comes from the marker's own label
#: in the field registry, and the two do not always match. Empty since the ``farm_profile``
#: retirement — its ``parcel_number``/``identification`` and ``county``/``region_polygon_ref``
#: were the only pairs that differed. Every field now offered is named the same on both sides,
#: so ``_editable_rows`` falls through to the key itself. Kept because the next renamed field
#: belongs here, and a form showing blank for a slot that holds data is the bug it prevents.
_RUNTIME_FIELD_SOURCE: dict[str, str] = {}


def _node_lonlat(documents: dict[str, Any], msn_id: str) -> dict[str, float] | None:
    """The node's own coordinate as (lon, lat), from its ag profile, or ``None``.

    58 of the 235 nodes publish no ag profile and therefore have no coordinate. Returning
    ``None`` says so; a zeroed pair would put a farm stand in the Gulf of Guinea.
    """
    document = documents.get(_dir.AG_PROFILE_DOCUMENT)
    for row in getattr(document, "rows", ()) or ():
        raw = getattr(row, "raw", None)
        head = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], list) else []
        pairs: dict[str, str] = {}
        for i in range(1, len(head) - 1, 2):
            pairs.setdefault(str(head[i]), "" if head[i + 1] is None else str(head[i + 1]))
        if pairs.get("rf.3-1-2") != msn_id:
            continue
        decoded = decode_hops_coordinate_token(pairs.get("rf.3-1-1", ""))
        if decoded:
            return {"lon": float(decoded["longitude"]["value"]),
                    "lat": float(decoded["latitude"]["value"])}
    return None


def build_detail_payload(documents: dict[str, Any], model: _dir.RegistryDirectoryModel,
                         msn_id: str, *, all_documents: list[Any]) -> dict[str, Any]:
    profile = _dir.build_profile(all_documents, msn_id, model=model)
    lcl = model.lcl_labels
    return {
        "schema": _SCHEMA,
        "tool_id": TOOL_ID,
        "mode": "detail",
        "node_param": NODE_PARAM,
        "back": {"label": "Back to nodes", "param": NODE_PARAM, "value": ""},
        "msn_id": msn_id,
        "title": profile.title or msn_id,
        "identity": [{"label": label, "value": value} for label, value in profile.identity],
        # The place chain is READ-ONLY here on purpose. Every rung is an msn segment, so
        # changing one is a re-addressing of the node and everything under it — a migration,
        # not a field edit. Showing it says where the node stands and, when a rung reads wrong,
        # names exactly which one.
        "place": [
            {"depth": level.depth, "band": level.band, "node": level.node,
             "label": level.label, "has_polygon": level.has_polygon}
            for level in profile.place
        ],
        "contains": [dict(entry) for entry in profile.contains],
        "entries": _editable_rows(profile),
        "events": _events_for(documents, msn_id),
        "routes": {
            "save_entry": SAVE_ENTRY_ROUTE,
            "create_event": CREATE_EVENT_ROUTE,
            "save_event": SAVE_EVENT_ROUTE,
            "delete_event": DELETE_EVENT_ROUTE,
        },
        "event_options": {
            "structures": [{"value": s, "label": label}
                           for s, label in _STRUCTURE_LABELS.items()],
            "classes": [{"value": c, "label": lcl.get(c, c)}
                        for c in _CLASS_ORDER if c in lcl] or
                       [{"value": c, "label": c} for c in _CLASS_ORDER],
            "kinds": [{"value": k, "label": label} for k, label in _KIND_LABELS.items()],
            "units": [{"value": u, "label": label} for u, label in _UNIT_LABELS.items()],
        },
        # A new event defaults to the node's own coordinate: a farm stand is at the farm unless
        # somebody says otherwise, and making the operator retype a coordinate invites a typo.
        "default_coordinate": _node_lonlat(documents, msn_id),
        "editable_documents": sorted(EDITABLE_FIELDS),
    }


# --------------------------------------------------------------------------- #
class ProfileAdminEditViewer:
    """Browse the registry, edit a node's entries, add and change its events."""

    tool_id = TOOL_ID
    writes = (
        DeclaredWrite(document_kind="registrar_profile", action="save_profile_entry"),
        DeclaredWrite(document_kind="registrar_event", action="create_event"),
        DeclaredWrite(document_kind="registrar_event", action="save_event"),
        DeclaredWrite(document_kind="registrar_event", action="delete_event"),
    )
    label = "Profile Admin"
    summary = "Browse any registry node and curate its profile entries and events."
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = REGISTRAR

    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # The registrar sandbox and nothing else: every document this tool draws is one
        # (2026-09-20; the whole-catalog read parsed the 138 MB blob for its 46 MB share).
        documents, err = read_sandbox_catalog(
            authority_db_file, tenant_id=_TENANT_DEFAULT, sandbox=_dir.SANDBOX)
        if err:
            return _notice(err)
        by_name = _dir.registrar_documents(documents)
        if not by_name:
            return _notice("the registrar sandbox is not readable from here")
        model = _dir.build_directory_model(documents)
        query = extra_query or {}
        node = _as_text(query.get(NODE_PARAM))
        if node:
            return build_detail_payload(by_name, model, node, all_documents=list(documents))
        return build_browse_payload(model, region=_as_text(query.get(REGION_PARAM)),
                                    needle=_as_text(query.get(QUERY_PARAM)))


register(ProfileAdminEditViewer())
