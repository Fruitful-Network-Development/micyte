"""What the portal's icon sprite contains — the one statement of it.

The rail draws its glyphs from a single sprite by external ``<use>``, and an external
``<use>`` pointing at a symbol the sprite does not contain **instantiates an empty box,
draws nothing, and reports nothing**. No console error, no network failure, no exception:
the slot is simply blank, and it looks like a CSS problem.

So membership has to be decided somewhere that knows the sprite's contents, and the browser
is not that place — the renderer has only a URL. This is that place, and the builder reads
the same table, so "what the sprite has" and "what the server is willing to name" cannot
drift apart. ``test_portal_icon_sprite`` rebuilds and byte-compares to keep the built file
in step with it.

Measured before this existed: `activity_icon_id_for_surface` can return ``workbench_ui`` and
a per-farm tool, neither of which is in the sprite; ``ExportManager.tool_id`` is
``export`` while the sprite carries ``export_manager``; and of the channels only ``agnet``
has a glyph, so a second channel was blank by construction. Three live blank slots, none of
them visible to any test.
"""

from __future__ import annotations

#: ``symbol id -> source leaflet stem``.
#:
#: A CLASS gets a glyph; an archetype inherits its class's; a tool declares its own. Where a
#: class has no glyph of its own it is absent here and resolution falls to its parent, which
#: is the same rule the viewscope lookup uses one layer down.
#:
#: A bare stem means the ``mycite-ui`` pool; a stem carrying a dot names its pool explicitly,
#: which is how the taxonomy reaches ``mycite-ag-family`` for the one glyph the UI pool has
#: no plant for.
SYMBOLS: dict[str, str] = {
    # --- the five root surfaces + the rail's furniture --------------------------------
    # (2026-08-21: the rail became exactly the five fixed surfaces — Compendium wears
    # the server rack, Utilities a plain gear, Network the MiCyte spore mark, and the
    # two new roots bring their own glyphs. The old `system` / `network` / `settings`
    # leaflets stay in the pool for the kind_* tree below.)
    "system": "mycite.server",
    "network": "micyte_mark",
    "utilities": "gear",
    "gallery": "gallery",
    "profile_interface": "profile_circle",
    "generic": "mss_box_datum_samras",
    "workbench_ui": "mss_tdatum_table",
    # --- core tools and channels (icon_id is the tool_id unless the tool declares one) --
    # (agro_calendar, home_config and rolodex left with the calendar-only rail,
    # 2026-08-16 — their capacities render through the document layer now.)
    "calendar": "calendar",
    "lcl_editor": "sort_relationship",
    "sources_manager": "link",
    "quiar": "tools",  # was handyman_erp; the glyph outlived the vertical's name
    "brevat": "pos",   # the generalized ERP hub — a till, the selling end
    # Enchir is the OTHER end from brevat: not a till, a body of work. `content_engine`
    # is used by no other entry — checked against the table rather than assumed, after a
    # first pass reached for `gallery`, which the Gadgets root already holds. A borrowed
    # icon is two things that look alike in a tree, which is what this table prevents.
    "enchir": "content_engine",
    "oveure": "edit",  # the knowledge shelf — a pencil, the writing end
    "quiar_overview": "tools",
    "project_manager": "tools",
    "contacts_manager": "profile",
    "job_manager": "tools",
    # `export`, not `export_manager`: the rail sends a tool's id, and ExportManager's is
    # `export`. The sprite carried the module name, so that slot drew nothing.
    "export": "archive",
    "agnet": "broadcast",
    "grantor": "subject_congregation",  # the roster of client aliases the channel serves
    # The convention (TASK-2026-09-11-001 P4): one id serves the surface AND the open
    # channel that offers it up — the base structure every tree is made of, a template.
    "convention": "sort_ztemplate",
    # --- the class tree ----------------------------------------------------------------
    "kind_profile": "profile",
    "kind_entity_profile": "organization",
    "kind_admin_entity_profile": "location",
    "kind_system_profile": "system",
    "kind_product_profile": "inventory",
    "kind_plantae_profile": "mycite-ag-family.leafy_green",
    "kind_project": "mss_stack",
    "kind_record": "pages",
    "kind_registry": "mss_tdatum_table",
    "kind_classification": "sort_relationship",
    "kind_contacts": "profile",
    "kind_roster": "subject_congregation",
    "kind_log": "time",
    "kind_invoice": "receipt",
    # WHAT MOVED, not what a thing is: `kind_product_profile` already holds the
    # crates (the product as a standing fact), so the movement log takes the parcels
    # — goods in transit in and out of a store (2026-09-12).
    "kind_stock_log": "mss_box_datumzparcels",
    "kind_offer": "pos",  # the standing offers — the selling end, like the market log
    "kind_note": "edit",
    "kind_planting": "location",  # a batch put somewhere — the siting end
    # Its OWN glyph, not the registry's table or the log's clock: a class that borrows
    # another's icon is two classes that look alike in a tree, which is the one thing
    # these are here to prevent.
    "kind_site_analytics": "mycite.analytics",
    # The standing arrangement, not the receipt — `kind_invoice` already holds that.
    "kind_subscription": "billing",
    "kind_drawing": "mycite.image",
    "kind_event_log": "calendar",
    "kind_network_log": "network",
    "kind_job_log": "tools",
    # A DOOR, and its own: `home` was unclaimed in the pool (99 stems were, measured
    # 2026-09-02 against this table's values), and a canvassing log is precisely a list of
    # houses. Borrowing `kind_job_log`'s wrench would have put two different classes side
    # by side in one instance's tree wearing one mark, which is what every note in this
    # table is about.
    "kind_canvass_log": "home",
    # A JOB AS A DOCUMENT, and its service lines. Distinct glyphs on purpose: `kind_job_log`
    # already holds `tools`, which five entries in this table share, and the note above
    # says why that matters — "a class that borrows another's icon is two classes that look
    # alike in a tree". Measured 2026-09-02 on the deployed activity rail, where `quiar`
    # and `job_manager` both resolved to `tools` and drew the same wrench side by side.
    # `contract` is the agreed piece of work; `hardware` is one service performed under it.
    "kind_job_profile": "contract",
    "kind_job_service": "hardware",
    "kind_market_log": "pos",          # a till, not a generic payment card
    "kind_event": "ticket",
    "kind_measure": "mss_lense_spacial",
}

#: What a rail item falls back to. The sprite must always contain it — if the fallback is
#: itself missing, every unknown id draws nothing and the fallback has achieved nothing.
GENERIC_ICON_ID = "generic"


def icon_id_or_generic(icon_id: object) -> str:
    """``icon_id`` when the sprite has it, else the generic glyph.

    Decided HERE rather than in the renderer, which knows only a URL. The renderer's comment
    used to claim "the sprite either has that symbol or the generic one is used"; nothing
    implemented the second half, and the ``if/else`` chain that had — drawing a circle for
    anything it did not know — was deleted when the sprite replaced it.
    """
    token = str(icon_id or "").strip()
    return token if token in SYMBOLS else GENERIC_ICON_ID


__all__ = ["GENERIC_ICON_ID", "SYMBOLS", "icon_id_or_generic"]
