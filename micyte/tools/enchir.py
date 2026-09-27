"""Enchir — the projects an instance offers up to its website, and the tree they hang on.

Operator, 2026-09-01: *"a new application called 'Enchir' for people like KKO and BHN to
manage projects and how they are offered up to their websites."* Operator, 2026-09-10:
*"The Enchir Application has far too many tabs, in fact it should only have 2. It should
have the local domain graph surface, then the projects tab. … A user should have a gallery
of projects, where the application's purpose is simply meant to interface with resources
and projects that get exported to website via a configured key."*

**TWO TABS.** Until 2026-09-10 this hub listed every document the sandbox held, grouped
by the archetype its rows folded to — a manager's view of the corpus. That was the wrong
subject: a client opening Enchir wants their projects as the website shows them, and the
tree they are arranged on. The document census is gone; the Compendium lists documents.

* **Domain** — the sandbox's own tree (`lcl_editor`, the same surface Oveure and Quiar
  host), opened for a PROJECT: the conventionalized base branches (`meta`, `classes`)
  arrive collapsed, and the selection defaults to the `project` node under `objects` when
  the tree has grown one, else to `objects` itself. Image pointer nodes under the objects
  branch — the operator's two-step ("the doc node is created then the pointer nodes under 3
  are created for easier access visually") — are the editor's own verbs once the artifact
  binary exists; this tab is where they will be arranged.
* **Projects** — a gallery of the site's project profiles, each opening to its own page:
  the feature image, the title, the photographs in the order the site shows them (the
  tour last), the two descriptions. Every save is one `profile.edit` through the
  `site_hosting` port, which the host hands over as context exactly as PIM's Design tab
  receives it. Nothing here learns where a leaflet lives.

  A photograph is ADDED from the page (2026-09-11) in the operator's two steps: the bytes
  go to the site through `asset.upload` with the project's slug, which lands the file in
  the site's pool and appends it to the profile; then the same bytes are kept as an
  `art.` document with a slot under the tree's `image` kind (`file_artifact`, the
  editor's own verb), and the Domain tab is where the slot is hung on a node. The second
  step is reported on its own: a site that has the picture and books that refused it is
  two facts, and the page says both.

**IT STILL READS NO LEAFLET.** This module ships in the published package; the site
arrives through the Protocol (`SiteProfile` in, `ProfileEdit` out), so a different filling
needs no edit here. Image addresses are the site's own — `<site>/assets/images/…` — and
the page shows them from the site, which is the only copy there is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from micyte.ports.site_hosting import OPERATION_ASSET_UPLOAD, OPERATION_PROFILE_EDIT
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE
from micyte.tools._registry import register
from micyte.tools._shared.utilities import as_text

_SCHEMA = "mycite.v2.portal.workbench.tool.enchir.v1"

#: Which tab is showing, and which project profile is open on the Projects tab.
TAB_QUERY = "enchir_kind"
PROJECT_QUERY = "enchir_project"
DOMAIN_TAB = "domain"
PROJECTS_TAB = "projects"
DEFAULT_TAB = DOMAIN_TAB

#: The port the Projects tab reads and writes through, and the door its page posts to.
#: The operator's route; the client door's repointer rewrites it (`_repoint_client_forms`).
PORT_ID = "site_hosting"
SITE_ROUTE = "/portal/api/v2/site"

#: Profile kinds that are the site's OWNER rather than something it offers up. A
#: construction company's own entity leaflet sits in the same manifest section as its
#: four homes; it is who they are, not a project, and the gallery does not show it.
_OWNER_KINDS = frozenset({"legal_entity", "natural_entity"})

#: The base structure's branches a project owner does not arrange, and the node the tree
#: is opened AT. Found by label on the tree the surface draws — a tree that has not grown a
#: `project` node yet opens at `objects`, which is where one would be minted.
_CONVENTIONAL_LABELS = frozenset({"meta", "classes"})
_OBJECTS_LABEL = "objects"
_PROJECT_LABELS = frozenset({"project", "projects"})


def _status_word(status: str) -> str:
    """What a person calls it. The leaflet says `for_sale`; the site says For sale."""
    return status.replace("_", " ").capitalize() if status else ""


def _site_origin(profiles: list[Any]) -> str:
    """``https://<domain>`` from any profile's page address, or ``""``.

    The site's own origin is what an image address is relative to; the port states a
    page URL per profile and nothing else about where the site lives.
    """
    for profile in profiles:
        parts = urlsplit(as_text(getattr(profile, "url", "")))
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    return ""


class Enchir:
    """The instance's projects, as the website offers them up, and the tree beneath."""

    tool_id = "enchir"
    label = "Enchir"
    summary = (
        "Your projects as your website shows them — the picture that stands for each, "
        "the order of the rest, the words beside them — and the tree they hang on."
    )
    route = WORKBENCH_UI_TOOL_ROUTE
    container = "tabbed"
    #: Launched against the INSTANCE, not offered for one document in focus. An empty
    #: tuple is what makes a tool universal (`_archetype.tool_matches_document`).
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True
    #: The site port arrives through host context, the declared way for a tool in the
    #: published package to be handed something it cannot reach for itself.
    wants_host_context = True

    def build_panel_payload(
        self,
        *,
        authority_db_file: Path | None = None,
        sandbox_id: str = "",
        document_id: str = "",
        datum_address: str = "",
        extra_query: dict[str, Any] | None = None,
        host_context: dict[str, Any] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        query = dict(extra_query or {})
        sandbox = as_text(sandbox_id)
        wanted = as_text(query.get(PROJECT_QUERY))
        tabs = [
            {"id": DOMAIN_TAB, "label": "Domain", "tool_id": "lcl_editor",
             "panel_payload": self._domain_pane(
                 authority_db_file=authority_db_file, sandbox=sandbox,
                 document_id=document_id, datum_address=datum_address, query=query)},
            {"id": PROJECTS_TAB, "label": "Projects", "tool_id": self.tool_id,
             "panel_payload": self._projects_pane(host_context, sandbox=sandbox, wanted=wanted)},
        ]
        active = as_text(query.get(TAB_QUERY)) or DEFAULT_TAB
        if wanted:
            active = PROJECTS_TAB
        if active not in (DOMAIN_TAB, PROJECTS_TAB):
            active = DEFAULT_TAB
        return {
            "schema": _SCHEMA,
            "container": "tabbed",
            "title": "Enchir",
            "sandbox_id": sandbox,
            "tab_query_param": TAB_QUERY,
            "active_tab": active,
            "tabs": tabs,
        }

    # ---- Domain ------------------------------------------------------------------------

    def _domain_pane(self, *, authority_db_file: Path | None, sandbox: str,
                     document_id: str, datum_address: str, query: dict[str, Any]) -> dict[str, Any]:
        """The tree, opened for a project.

        `lcl_editor` builds the surface; this only says how it OPENS: the conventionalized
        branches collapsed and the selection on the project node. Both are hints the
        renderer takes when the person has not chosen otherwise — a selection in the query
        is theirs and is left alone.
        """
        from micyte.tools.lcl_editor import LclEditorViewer

        if not authority_db_file or not sandbox:
            return {"schema": _SCHEMA, "container": "record_table", "title": "Domain",
                    "columns": ["node"], "rows": [], "row_count": 0,
                    "empty_text": "Enchir opens one sandbox's tree, and this render named none."}
        try:
            payload = LclEditorViewer().build_panel_payload(
                authority_db_file=authority_db_file, sandbox_id=sandbox,
                document_id=document_id, datum_address=datum_address, extra_query=query)
        except Exception as exc:                       # reported, never raised at a client
            return {"schema": _SCHEMA, "container": "record_table", "title": "Domain",
                    "columns": ["node"], "rows": [], "row_count": 0,
                    "empty_text": f"this sandbox's tree could not be read ({exc})"}
        nodes = [n for n in (payload.get("nodes") or []) if isinstance(n, dict)]
        collapse, focus = self._opening(nodes)
        payload["collapse"] = collapse
        if focus and not as_text(payload.get("selected_node")):
            payload["selected_node"] = focus
        return payload

    @staticmethod
    def _opening(nodes: list[dict[str, Any]]) -> tuple[list[str], str]:
        """``(branches to collapse, node to open at)`` read off the tree by label."""
        roots = {as_text(n.get("full_slug")) for n in nodes if not as_text(n.get("parent_slug"))}
        collapse: list[str] = []
        objects = ""
        for node in nodes:
            slug, label = as_text(node.get("full_slug")), as_text(node.get("label")).lower()
            if as_text(node.get("parent_slug")) not in roots:
                continue
            if label in _CONVENTIONAL_LABELS:
                collapse.append(slug)
            elif label == _OBJECTS_LABEL:
                objects = slug
        focus = ""
        if objects:
            focus = next((as_text(n.get("full_slug")) for n in nodes
                          if as_text(n.get("parent_slug")) == objects
                          and as_text(n.get("label")).lower() in _PROJECT_LABELS), objects)
        return collapse, focus

    # ---- Projects ----------------------------------------------------------------------

    def _projects_pane(self, host_context: dict[str, Any] | None, *,
                       sandbox: str, wanted: str) -> dict[str, Any]:
        """The site's projects as a gallery, or the one that is open as its page.

        A seam that REFUSES reads as a refusal, never as "no projects"; a site not yet
        connected says so in the client's words.
        """
        context = host_context if isinstance(host_context, dict) else {}
        provider = context.get("port")
        if not callable(provider):
            return self._gallery([], why="this render was offered no site, so there is nothing to show yet")
        try:
            port = provider(PORT_ID)
        except Exception as exc:                  # the host's own refusal, its own words
            return self._gallery([], why=str(exc))
        if port is None:
            return self._gallery([], why=(
                "your site is not connected here yet. Your operator is setting up the "
                "connection that lets this app reach it."))
        lister = getattr(port, "list_profiles", None)
        if not callable(lister):
            return self._gallery([], why="your site's connection does not offer its profiles here yet")
        try:
            profiles = list(lister())
        except PermissionError as exc:
            return self._gallery([], why=f"this instance is not permitted to read them ({exc})")
        except Exception as exc:
            return self._gallery([], why=f"your site's profiles could not be read ({exc})")
        projects = [p for p in profiles if as_text(getattr(p, "kind", "")) not in _OWNER_KINDS]
        origin = _site_origin(profiles)
        opened = next((p for p in projects if as_text(getattr(p, "slug", "")) == wanted), None)
        if opened is not None:
            return self._page(opened, origin=origin, sandbox=sandbox)
        return self._gallery(projects, origin=origin)

    def _gallery(self, projects: list[Any], *, origin: str = "", why: str = "") -> dict[str, Any]:
        cards = []
        for p in projects:
            refs = list(getattr(p, "gallery_refs", ()) or ())
            hidden = {r for r in (getattr(p, "gallery_hidden_refs", ()) or ()) if r in refs}
            shown = [r for r in refs if r not in hidden]
            feature = as_text(getattr(p, "feature_ref", "")) or (shown[0] if shown else "")
            names = dict(getattr(p, "gallery_names", {}) or {})
            cards.append({
                "slug": as_text(getattr(p, "slug", "")),
                "name": as_text(getattr(p, "name", "")) or as_text(getattr(p, "slug", "")),
                "status": as_text(getattr(p, "status", "")),
                "status_word": _status_word(as_text(getattr(p, "status", ""))),
                "photographs": len(shown),
                "hidden": len(hidden),
                "feature": {"src": (origin + feature) if (origin and feature) else "",
                            "name": names.get(feature) or feature},
                "url": as_text(getattr(p, "url", "")),
            })
        return {
            "schema": _SCHEMA,
            "container": "project_gallery",
            "title": "Projects on your site",
            "site": origin,
            "count_label": f"{len(cards)} on your site" if cards else "",
            "pick_param": PROJECT_QUERY,
            "projects": cards,
            "empty_text": why or (
                "Your site has no project profiles yet. When a project is ready to "
                "show, its profile is added to your site and appears here to arrange."),
        }

    def _page(self, profile: Any, *, origin: str, sandbox: str) -> dict[str, Any]:
        """ONE project, opened: what the site shows and every way to arrange it.

        One page and one save, deliberately. The first cut drew three forms (feature,
        order, descriptions) stacked under a table, and the operator called opening a
        project "very clunky and odd". A project is one thing; its page is one thing; the
        save carries every field the page holds, and the door leaves the rest of the
        leaflet alone.

        Photographs are named the way the port names them (`gallery_names`) and sent
        back by that name, one per line, `#` in front of a hidden one — the door's own
        vocabulary, so nobody retypes a pool path. The tour is LAST and not movable: the
        site closes its gallery with it.
        """
        slug = as_text(getattr(profile, "slug", ""))
        refs = list(getattr(profile, "gallery_refs", ()) or ())
        hidden = set(getattr(profile, "gallery_hidden_refs", ()) or ())
        names = dict(getattr(profile, "gallery_names", {}) or {})
        titles = dict(getattr(profile, "gallery_titles", {}) or {})
        feature = as_text(getattr(profile, "feature_ref", ""))
        extra = getattr(profile, "extra", None) or {}
        video = as_text(extra.get("video_embed"))
        return {
            "schema": _SCHEMA,
            "container": "project_page",
            "slug": slug,
            "name": as_text(getattr(profile, "name", "")) or slug,
            "marketing_name": as_text(extra.get("marketing_name")),
            "status": as_text(getattr(profile, "status", "")),
            "status_word": _status_word(as_text(getattr(profile, "status", ""))),
            "address": as_text(extra.get("address")),
            "url": as_text(getattr(profile, "url", "")),
            "site": origin,
            "back": {"label": "All projects", "param": PROJECT_QUERY, "value": ""},
            "feature": feature,
            "photographs": [{
                "ref": r,
                "src": (origin + r) if origin else "",
                "name": names.get(r) or r,
                "title": as_text(titles.get(r)),
                "hidden": r in hidden,
            } for r in refs],
            "video": ({"embed": video, "title": as_text(extra.get("video_title")) or "Tour"}
                      if video else None),
            "summary": as_text(getattr(profile, "summary", "")),
            "bio": "\n\n".join(as_text(p) for p in (getattr(profile, "bio", ()) or ())),
            "submit": {
                "route": f"{SITE_ROUTE}/{OPERATION_PROFILE_EDIT}", "sandbox_id": sandbox,
                "success_label": "Saved", "fixed": {"slug": slug},
            },
            "upload_action": self._upload_action(
                slug, sandbox=sandbox, document=as_text(extra.get("project_document"))),
            # The DOCUMENT this profile is derived from, when the export has run (P3):
            # the page is the same; a save is performed on the document and re-exported.
            "document": as_text(extra.get("project_document")),
        }

    @staticmethod
    def _upload_action(slug: str, *, sandbox: str, document: str = "") -> dict[str, Any]:
        """Where a new photograph goes, in two posts the renderer makes in order.

        The site first, by the operation's own name and with the slug fixed, so the
        file lands in the pool AND on the profile in one door; the books second, through
        the editor's `file_artifact` route — declared on the editor because the slot is a
        tree write, and carried here so the client holds no route of its own.
        """
        from micyte.tools.lcl_editor import ROUTES as _editor_routes

        record: dict[str, Any] = {"route": _editor_routes["file_artifact"], "kind": "image"}
        if document:
            # Document-backed: the picture joins the document's gallery as it is filed.
            record["project"] = document
            record["role"] = "gallery"
        return {
            "route": f"{SITE_ROUTE}/{OPERATION_ASSET_UPLOAD}", "sandbox_id": sandbox,
            "fixed": {"slug": slug}, "success_label": "Added", "record": record,
        }


register(Enchir())

__all__ = ["DEFAULT_TAB", "DOMAIN_TAB", "PORT_ID", "PROJECTS_TAB", "PROJECT_QUERY",
           "SITE_ROUTE", "TAB_QUERY", "Enchir"]
