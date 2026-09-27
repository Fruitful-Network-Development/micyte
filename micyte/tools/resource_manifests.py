"""The shared resource library, who uses each file, and what a delete would take.

## What this replaces

The legacy per-client dashboard's ``manifests_operator.js`` — the operator's only way to
browse the resource manifest, see which client sites use a leaflet, and delete an asset.
That tree is being retired (TASK-2026-08-28-002 phase C) and this is its portal successor.

## Why this is not a second surface

The ``ext_resources`` extension surface was dissolved in the portal-tool-overlay
restructure. Its payload builders (``resources_extension._resources_*_payload``) and the
``renderResourcesApp`` branch of ``v2_portal_workbench_renderers.js`` are still in the
tree, and as of 2026-08-29 **their only callers are tests** — source-present, runtime-dead.
Building on them would have produced a screen nothing renders.

So this composes what IS live: the shared container renderers (``tabbed`` / ``composite``
/ ``record_table`` / ``record_form``) and, behind the host seam, the same
``resources_extension`` / ``resource_types`` helpers the ``/__fnd/resources/*`` routes
call. No new renderer, no second reader of the manifest.

## It reaches nothing by itself

``micyte`` holds no filesystem and does not know where this deployment keeps its client
sites. The host hands over a ``resource_manifests`` reader on ``host_context`` — and hands
it over ONLY to the operator, so a client grantee's render finds nothing to call and the
tab says so. The routes it posts to check the same thing again, in their own words.

## The two deletes are two different acts

They are named here by what they mean rather than by their routes:

* **Shared library** (``asset/delete-global``) — the file lives in the pool every client
  site draws from. Deleting it can take an image off several live sites at once, so the
  pane lists exactly which ones and refuses to imply safety it has not measured.
* **This site's own file** (``asset/delete-own``) — the file lives inside one client's own
  site tree and only that site's pages can reference it. The pane counts those pages.

Both go through the shared typed-confirmation modal (``submit_action.confirm``), and both
land on routes that check the typed text again server-side.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._registry import register

_SCHEMA = "mycite.v2.portal.workbench.tool.resource_manifests.v1"

#: Each level of the drill-down owns its own query parameter. Sharing one would make
#: opening a leaflet in the library also move the Sites tab's selection — the collision
#: every nested hub in this package avoids the same way.
TAB_QUERY = "manifest_section"
NODE_QUERY = "manifest_node"
ASSET_QUERY = "manifest_asset"
KIND_QUERY = "manifest_kind"
SITE_QUERY = "manifest_site"
FILE_QUERY = "manifest_file"

DEFAULT_TAB = "library"

#: Where the two deletes are posted. The routes judge the caller and re-check the typed
#: confirmation; this only says which door.
_LIBRARY_DELETE_ROUTE = "/__fnd/resources/manifest/delete-library-asset"
_SITE_DELETE_ROUTE = "/__fnd/resources/manifest/delete-site-file"


def _as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def manifest_reader(host_context: dict[str, Any] | None) -> tuple[Any, str]:
    """``(reader, why_not)`` — the manifest seam this render may use, or why it may not.

    The refusal is CARRIED rather than swallowed. An empty library and a library this
    caller is not allowed to see want opposite actions from whoever is reading, and a pane
    that renders "nothing here" over the second teaches the operator their pool is empty.
    """
    context = host_context if isinstance(host_context, dict) else {}
    reader = context.get("resource_manifests")
    if reader is None:
        return None, (
            "this surface reads every client's site manifests, so the portal offers it "
            "only to the operator. Nothing was handed to this render.")
    return reader, ""


def _notice(title: str, text: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "record_table", "title": title,
            "columns": ["note"], "rows": [], "row_count": 0, "count_label": "",
            "empty_text": text}


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _table(title: str, columns: list[str], rows: list[dict[str, Any]],
           **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": _SCHEMA, "container": "record_table", "title": title,
        "columns": columns, "rows": rows, "row_count": len(rows),
    }
    payload.update(extra)
    return payload


def _back(label: str, param: str) -> dict[str, str]:
    """Clearing the parameter IS the way back — the same return `pim_design` uses."""
    return {"label": label, "param": param, "value": ""}


# ------------------------------------------------------------------- library ---
def _node_pane(reader: Any) -> dict[str, Any]:
    nodes = reader.type_nodes()
    rows = [
        {
            # The tree's shape carried in the label, because a record_table draws flat
            # rows: without the indent, "Image" and "Boutique Homes" read as siblings.
            "type": ("· " * int(node["depth"])) + node["label"],
            "leaflets": node["count"] or "",
            "address": node["full_slug"],
        }
        for node in nodes
    ]
    return _table(
        "The shared library, by type",
        ["type", "leaflets", "address"],
        rows,
        count_label=_plural(len(rows), "node"),
        empty_text="No leaflet types on disk — the shared site-core pool is empty.",
        notice=(
            "Every leaflet the network shares, filed by the naming convention: type, then "
            "the client that owns it, then the name. Open a node to see what is under it."),
        pick={
            "label": "Open", "param": NODE_QUERY, "go_label": "Open",
            "options": [
                {"value": node["full_slug"],
                 "label": f"{node['label']} ({node['count']})" if node["count"] else node["label"]}
                for node in nodes
            ],
        },
    )


def _leaflets_pane(reader: Any, node: str) -> dict[str, Any]:
    leaflets = reader.node_leaflets(node)
    rows = [
        {
            "leaflet": row["display_name"],
            "file": row["filename"],
            "owner": row["owner"] or "—",
            # STATED, not hidden. The tree lists galleries the delete gate does not
            # manage (schema, newsletter); the legacy tab fabricated a descriptor for
            # those and offered a Delete the backend refused every time.
            "managed": "yes" if row["manageable"] else "read-only",
        }
        for row in leaflets
    ]
    return _table(
        node,
        ["leaflet", "file", "owner", "managed"],
        rows,
        count_label=_plural(len(rows), "leaflet"),
        empty_text="Nothing directly under this node — open one of its children.",
        back=_back("All types", NODE_QUERY),
        pick={
            "label": "Open", "param": ASSET_QUERY, "go_label": "Open",
            "options": [{"value": row["asset_path"],
                         "label": f"{row['display_name']} — {row['filename']}"}
                        for row in leaflets],
        },
    )


def _library_delete_form(row: dict[str, Any], usage: dict[str, Any], *,
                         force: bool) -> dict[str, Any]:
    """One of the two shared-library delete verbs, with what it would actually take.

    The distinction is not "force" as a flag but what happens to the client sites listed
    above it: without it the backend refuses while any of them still lists the leaflet;
    with it, every one of them loses the leaflet first and then the file goes.
    """
    filename = row["filename"]
    sites = usage["sites"]
    named = ", ".join(entry["client"] or entry["site"] for entry in sites)
    if sites:
        who = f"{_plural(len(sites), 'client site')} list this leaflet: {named}."
    else:
        who = "No client site lists this leaflet in its manifest."
    if force:
        title = "Delete it, and take it off every site that uses it"
        what = (
            f"{who} Every one of them loses it, and then the shared file is deleted. "
            "Anywhere those sites showed it goes blank until it is replaced.")
    else:
        title = "Delete it from the shared library"
        what = (
            f"{who} "
            + ("This refuses while any of them still lists it — de-allocate them first, "
               "or use the other form below, which does it for you."
               if sites else
               "Nothing to de-allocate first, so this deletes the shared file."))
    if usage["excerpt_count"]:
        what += (
            f" It also has {_plural(usage['excerpt_count'], 'page-content excerpt')}, "
            "which blocks the delete either way — remove those first.")
    what += " The pool is git-tracked, so the file is recoverable from history."
    return {
        "schema": _SCHEMA, "container": "record_form", "title": title,
        "fields": [],
        "submit_label": "Delete from every site, then delete the file" if force
                        else "Delete permanently",
        "submit_action": {
            "route": _LIBRARY_DELETE_ROUTE, "danger": True, "success_label": "Deleted",
            "fixed": {"gallery": row["gallery"], "filename": filename,
                      "force": bool(force)},
            # The FILENAME, not the display name: two leaflets can share a display name
            # and only one of them is being deleted.
            "confirm": {"expect": filename, "key": "confirm", "text": what},
        },
    }


def _leaflet_pane(reader: Any, node: str, asset_path: str) -> dict[str, Any]:
    row = reader.leaflet(node, asset_path)
    if row is None:
        # A stale link — deleted, or renamed by an edit. Say so and show the node it came
        # from rather than an empty pane that reads as a fault.
        pane = _leaflets_pane(reader, node)
        pane["notice"] = (
            f"{asset_path} is no longer under this node — it may have been renamed or "
            "deleted. Here is what is there now.")
        return pane
    usage = reader.usage(row["kind"], row["asset_path"])
    facts = _table(
        row["display_name"],
        ["fact", "value"],
        [
            {"fact": "file", "value": row["filename"]},
            {"fact": "served at", "value": row["asset_path"]},
            {"fact": "type", "value": row["full_type"] or "—"},
            {"fact": "owner", "value": row["owner"] or "—"},
            {"fact": "size", "value": f"{row['size_bytes'] // 1024} KB"
                                      if row["size_bytes"] else "—"},
        ],
        count_label="shared library",
        back=_back("Back to the list", ASSET_QUERY),
    )
    used_rows = [{"client": entry["client"] or "—", "site": entry["site"],
                  "listed as": entry["asset_id"] or "—"} for entry in usage["sites"]]
    if usage["excerpt_count"]:
        blocked = (f"It also has {_plural(usage['excerpt_count'], 'page-content excerpt')} "
                   "derived from it, which blocks a delete on its own.")
    elif used_rows:
        blocked = "Deleting it takes it off every site listed here."
    else:
        blocked = "Nothing lists it, so deleting it takes nothing off a live site."
    used = _table(
        "Which client sites use it",
        ["client", "site", "listed as"],
        used_rows,
        count_label=_plural(len(used_rows), "site"),
        empty_text="No site manifest lists this leaflet.",
        notice=blocked,
    )
    panes: list[dict[str, Any]] = [{"panel_payload": facts}, {"panel_payload": used}]
    if row["manageable"]:
        panes.append({"panel_payload": _library_delete_form(row, usage, force=False)})
        panes.append({"panel_payload": _library_delete_form(row, usage, force=True)})
    else:
        panes.append({"panel_payload": _notice(
            "This one cannot be deleted here",
            f"{row['gallery'] or 'its gallery'} is not one the delete gate manages, so no "
            "form is offered — a button the backend refuses every time is worse than none.",
        )})
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": panes}


def _library_pane(reader: Any, why_not: str, query: dict[str, Any]) -> dict[str, Any]:
    if reader is None:
        return _notice("Library", why_not)
    node = _as_text(query.get(NODE_QUERY))
    asset = _as_text(query.get(ASSET_QUERY))
    if node and asset:
        return _leaflet_pane(reader, node, asset)
    if node:
        return _leaflets_pane(reader, node)
    return _node_pane(reader)


# ------------------------------------------------------------------- catalog ---
def _catalog_pane(reader: Any, why_not: str, query: dict[str, Any]) -> dict[str, Any]:
    """The pool a site can be allocated FROM, one manifest kind at a time."""
    if reader is None:
        return _notice("Allocatable", why_not)
    kinds = list(reader.catalog_kinds())
    kind = _as_text(query.get(KIND_QUERY)) or (kinds[0] if kinds else "")
    rows = [
        {"leaflet": row.get("display_name") or row.get("filename"),
         "file": row.get("filename"),
         "allocate as": row.get("asset_id"),
         "served at": row.get("asset_path")}
        for row in (reader.catalog(kind) if kind else [])
    ]
    return _table(
        f"Allocatable — {kind}" if kind else "Allocatable",
        ["leaflet", "file", "allocate as", "served at"],
        rows,
        count_label=_plural(len(rows), "leaflet"),
        empty_text=f"Nothing of kind {kind!r} in the shared pool."
                   if kind else "No allocatable kinds.",
        notice=(
            "What a site can be given, for one kind at a time. Profiles are listed only "
            "when they are public — allocating a non-public one writes a manifest entry "
            "that never renders."),
        pick={"label": "Kind", "param": KIND_QUERY, "go_label": "Show",
              "options": [{"value": name, "label": name} for name in kinds]},
    )


# --------------------------------------------------------------------- sites ---
def _sites_pane(reader: Any) -> dict[str, Any]:
    sites = reader.sites()
    rows = [{"client": row["client"] or "—", "site": row["site"],
             "shared leaflets": row["allocated"], "own files": row["own_files"]}
            for row in sites]
    return _table(
        "Client sites",
        ["client", "site", "shared leaflets", "own files"],
        rows,
        count_label=_plural(len(rows), "site"),
        empty_text="No client sites under this webapps root.",
        notice=(
            "What each site is allocated out of the shared pool, and how many files it "
            "keeps of its own. The two are deleted by different acts."),
        pick={"label": "Open", "param": SITE_QUERY, "go_label": "Open",
              "options": [{"value": row["site"],
                           "label": f"{row['client'] or row['site']} — {row['site']}"}
                          for row in sites]},
    )


def _site_pane(reader: Any, site: str) -> dict[str, Any]:
    allocations = reader.site_allocations(site)
    own = reader.site_own_images(site)
    allocated = _table(
        f"{site} — allocated from the shared pool",
        ["kind", "listed as", "served at"],
        [{"kind": row["kind"], "listed as": row["asset_id"] or "—",
          "served at": row["asset_path"]} for row in allocations],
        count_label=_plural(len(allocations), "allocation"),
        empty_text="This site is allocated nothing out of the shared pool.",
        notice=(
            "These files live in the shared pool and other sites may be allocated the "
            "same ones. Deleting one is a library act — do it from the Library tab, "
            "which shows who else would lose it."),
        back=_back("All sites", SITE_QUERY),
    )
    own_files = _table(
        f"{site} — its own files",
        ["file", "name", "referenced as"],
        [{"file": row["filename"], "name": row["display_name"],
          "referenced as": row["asset_path"]} for row in own],
        count_label=_plural(len(own), "file"),
        empty_text=(
            "This site keeps no files of its own — everything it shows comes out of the "
            "shared pool."),
        notice="These live inside this site's own tree. No other site can be using them.",
        pick={"label": "Open", "param": FILE_QUERY, "go_label": "Open",
              "options": [{"value": row["filename"], "label": row["filename"]}
                          for row in own]},
    )
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": allocated}, {"panel_payload": own_files}]}


def _site_file_pane(reader: Any, site: str, filename: str) -> dict[str, Any]:
    row = next((entry for entry in reader.site_own_images(site)
                if entry["filename"] == filename), None)
    if row is None:
        pane = _site_pane(reader, site)
        pane["panes"][1]["panel_payload"]["notice"] = (
            f"{filename} is no longer in {site}'s own files. Here is what is there now.")
        return pane
    usage = reader.own_image_usage(site, filename)
    facts = _table(
        f"{site} — {filename}",
        ["fact", "value"],
        [{"fact": "name", "value": row["display_name"]},
         {"fact": "referenced as", "value": row["asset_path"]},
         {"fact": "site", "value": site}],
        count_label="this site's own file",
        back=_back("Back to this site", FILE_QUERY),
    )
    pages = list(usage.get("pages") or [])
    if usage.get("measured") and usage.get("kind") == "manifest":
        # A manifest site renders every page from one JSON file. A hit there proves the
        # site references the image but names no page, so saying "0 pages" would be a
        # measurement this cannot make.
        where = ("This site's page manifest references it — it is in use, though which "
                 "page cannot be told from here."
                 if usage.get("manifest_hit")
                 else "This site's page manifest does not mention it.")
    elif usage.get("measured"):
        where = (f"{_plural(len(pages), 'page')} use this image: {', '.join(pages)}."
                 if pages else
                 f"None of the {usage.get('scanned', 0)} pages scanned mention it.")
    else:
        # NOT "safe". The docstring on delete_own_image says the file may still be
        # referenced by the live site's HTML, and if we could not read that HTML the only
        # honest thing to report is that we could not read it.
        where = ("This site's pages could not be read, so nothing here can tell whether "
                 "any of them use this file.")
    facts["notice"] = where
    delete = {
        "schema": _SCHEMA, "container": "record_form",
        "title": "Delete this site's own file",
        "fields": [],
        "submit_label": "Delete permanently",
        "submit_action": {
            "route": _SITE_DELETE_ROUTE, "danger": True, "success_label": "Deleted",
            "fixed": {"site": site, "filename": filename},
            "confirm": {
                "expect": filename, "key": "confirm",
                "text": (
                    f"This deletes {filename} out of {site}'s own site tree. It is that "
                    f"site's file and no other site can be using it. {where} "
                    "The tree is git-tracked, so the file is recoverable from history."),
            },
        },
    }
    return {"schema": _SCHEMA, "container": "composite", "direction": "column",
            "panes": [{"panel_payload": facts}, {"panel_payload": delete}]}


def _sites_tab(reader: Any, why_not: str, query: dict[str, Any]) -> dict[str, Any]:
    if reader is None:
        return _notice("Sites", why_not)
    site = _as_text(query.get(SITE_QUERY))
    chosen_file = _as_text(query.get(FILE_QUERY))
    if site and chosen_file:
        return _site_file_pane(reader, site, chosen_file)
    if site:
        return _site_pane(reader, site)
    return _sites_pane(reader)


class ResourceManifests:
    """The operator's manifest administration, as a portal surface."""

    tool_id = "resource_manifests"
    label = "Resource Manifests"
    summary = (
        "The shared leaflet library by type, which client sites use each one, what each "
        "site keeps of its own, and the two deletes — the shared file, and a site's own "
        "file — each stating what it would take off a live site before it takes it."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Launched by ADDRESS. It opens on no document at all: what it shows lives under the
    #: webapps root, which the store knows nothing about.
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: The host resolves the operator check and hands the reader over. See the module
    #: docstring — `micyte` cannot reach a client site tree.
    wants_host_context = True
    # No `writes`: a delete here removes a FILE under the webapps root, not a datum row.
    # `datum_write_policy` judges document kinds against sandbox grants and has nothing to
    # measure this with; the operator gate on the route is what authorizes it.

    def build_panel_payload(
        self, *, authority_db_file: Path | None = None, sandbox_id: str = "",
        document_id: str = "", datum_address: str = "",
        extra_query: dict[str, Any] | None = None,
        host_context: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        del authority_db_file, document_id, datum_address
        query = dict(extra_query or {})
        reader, why_not = manifest_reader(host_context)
        tabs = [
            # The library first: an operator arrives asking what exists and who has it far
            # more often than asking what one site holds.
            {"id": "library", "label": "Library", "tool_id": "resource_manifests_library",
             "panel_payload": _library_pane(reader, why_not, query)},
            {"id": "allocatable", "label": "Allocatable",
             "tool_id": "resource_manifests_catalog",
             "panel_payload": _catalog_pane(reader, why_not, query)},
            {"id": "sites", "label": "Sites", "tool_id": "resource_manifests_sites",
             "panel_payload": _sites_tab(reader, why_not, query)},
        ]
        active = _as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if active not in [tab["id"] for tab in tabs]:
            active = DEFAULT_TAB
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": self.label,
            "sandbox_id": _as_text(sandbox_id),
            "active_tab": active,
            "tab_query_param": TAB_QUERY,
            "tabs": tabs,
        }


register(ResourceManifests())
