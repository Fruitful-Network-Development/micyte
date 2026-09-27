"""Portal surface catalog and tool registry builders and resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from micyte.core.scalars import as_text

if TYPE_CHECKING:
    # Lazy at runtime to break the circular import with shell.py (Phase 12a).
    from .shell import PortalToolRegistryEntry

from .shell_schemas import (
    AGRO_ERP_TOOL_ENTRYPOINT_ID,
    AGRO_ERP_TOOL_ROUTE,
    AGRO_ERP_TOOL_SURFACE_ID,
    GADGETS_ROOT_ROUTE,
    GADGETS_ROOT_SURFACE_ID,
    NETWORK_BROWSER_ROUTE,
    NETWORK_BROWSER_SURFACE_ID,
    NETWORK_INBOX_ROUTE,
    NETWORK_INBOX_SURFACE_ID,
    NETWORK_P2P_ROUTE,
    NETWORK_P2P_SURFACE_ID,
    NETWORK_PROFILE_ROUTE,
    NETWORK_PROFILE_SURFACE_ID,
    NETWORK_ROOT_ROUTE,
    NETWORK_ROOT_SURFACE_ID,
    PROFILE_ROOT_ROUTE,
    PROFILE_ROOT_SURFACE_ID,
    REDUCER_OWNED_SURFACE_IDS,
    SYSTEM_ROOT_ROUTE,
    SYSTEM_ROOT_SURFACE_ID,
    TOOL_SURFACE_IDS,
    UTILITIES_APPS_ROUTE,
    UTILITIES_APPS_SURFACE_ID,
    UTILITIES_CONTRACTS_ROUTE,
    UTILITIES_CONTRACTS_SURFACE_ID,
    UTILITIES_EXTENSIONS_ROUTE,
    UTILITIES_EXTENSIONS_SURFACE_ID,
    UTILITIES_GRANTEE_PROFILE_ROUTE,
    UTILITIES_GRANTEE_PROFILE_SURFACE_ID,
    UTILITIES_PERIPHERALS_ROUTE,
    UTILITIES_PERIPHERALS_SURFACE_ID,
    UTILITIES_PORTS_ROUTE,
    UTILITIES_PORTS_SURFACE_ID,
    UTILITIES_PUBLISHED_ROUTE,
    UTILITIES_PUBLISHED_SURFACE_ID,
    UTILITIES_ROOT_ROUTE,
    UTILITIES_ROOT_SURFACE_ID,
    UTILITIES_TOOL_EXPOSURE_ROUTE,
    UTILITIES_TOOL_EXPOSURE_SURFACE_ID,
    UTILITIES_TOOLS_ROUTE,
    UTILITIES_TOOLS_SURFACE_ID,
    UTILITIES_WALLET_ROUTE,
    UTILITIES_WALLET_SURFACE_ID,
    WORKBENCH_UI_TOOL_ENTRYPOINT_ID,
    WORKBENCH_UI_TOOL_ROUTE,
    WORKBENCH_UI_TOOL_SURFACE_ID,
)
from .shell_state import PortalSurfaceCatalogEntry

# Phase 12a: PortalToolRegistryEntry now lives canonically in shell.py only.
# Top-level import would create a cycle (shell.py imports this module at
# module load), so the functions below resolve the class lazily.


def build_portal_surface_catalog(*, network_enabled: bool = True) -> tuple[PortalSurfaceCatalogEntry, ...]:
    # `network_enabled` gates the NETWORK root surface. DEFAULT True — zero
    # behaviour change. When an instance sets it False the NETWORK entry is
    # ABSENT from the catalog entirely, so it never paints in the activity bar
    # (the activity builder iterates this catalog) and never resolves as a
    # launchable surface. The flag is threaded from the instance config
    # (V2PortalHostConfig.network_enabled, read from private/config.json).
    #
    # The Network page IS the browser (convention section 4a): a browser of
    # msn_id nodes, with a P2P messaging centre beside it (4b). The pre-existing
    # root entry keeps its id and route so bookmarks and the activity bar are
    # undisturbed, but it is labelled for what it actually presents — a
    # contract/event LOG — rather than continuing to claim the page's name.
    network_root_entry: tuple[PortalSurfaceCatalogEntry, ...] = (
        (
            PortalSurfaceCatalogEntry(
                surface_id=NETWORK_ROOT_SURFACE_ID,
                label="Network",
                route=NETWORK_ROOT_ROUTE,
                root_surface_id=NETWORK_ROOT_SURFACE_ID,
                surface_kind="network_root",
                page_owner="network",
            ),
        )
        if network_enabled
        else ()
    )
    # The Network page's two tabs (convention section 4): a browser of msn_id
    # nodes, and the inter-instance messaging centre. They are SUB-surfaces, so
    # they sit with the other sub-surfaces below rather than among the three
    # roots — the catalog's shape is "roots first, then everything else", and the
    # activity bar depends on it.
    #
    # Gated by the same flag as the root: the network module is optional, and a
    # sub-surface that survived the flag would be a side door into a module the
    # instance turned off.
    network_tab_entries: tuple[PortalSurfaceCatalogEntry, ...] = (
        (
            # "Browser" is no longer a TAB (operator, 2026-08-17): the Network page is
            # the map, and this is where its GEAR leads. The surface, route and payload
            # are unchanged — the tab went, the capability did not — and the label now
            # says what the page is rather than what the map already does.
            PortalSurfaceCatalogEntry(
                surface_id=NETWORK_BROWSER_SURFACE_ID,
                label="Network settings",
                route=NETWORK_BROWSER_ROUTE,
                root_surface_id=NETWORK_ROOT_SURFACE_ID,
                surface_kind="network_browser",
                page_owner="network",
            ),
            PortalSurfaceCatalogEntry(
                surface_id=NETWORK_P2P_SURFACE_ID,
                label="P2P",
                route=NETWORK_P2P_ROUTE,
                root_surface_id=NETWORK_ROOT_SURFACE_ID,
                surface_kind="network_p2p",
                page_owner="network",
            ),
            # The map's other two destinations. INBOX carries what P2P and the System
            # Log tab held: contracts down the left, each one's history on the right.
            # PROFILE is this instance's own node, in the same card the map draws for
            # anyone else's.
            PortalSurfaceCatalogEntry(
                surface_id=NETWORK_INBOX_SURFACE_ID,
                label="Inbox",
                route=NETWORK_INBOX_ROUTE,
                root_surface_id=NETWORK_ROOT_SURFACE_ID,
                surface_kind="network_inbox",
                page_owner="network",
            ),
            PortalSurfaceCatalogEntry(
                surface_id=NETWORK_PROFILE_SURFACE_ID,
                label="This instance",
                route=NETWORK_PROFILE_ROUTE,
                root_surface_id=NETWORK_ROOT_SURFACE_ID,
                surface_kind="network_profile",
                page_owner="network",
            ),
        )
        if network_enabled
        else ()
    )
    return (
        PortalSurfaceCatalogEntry(
            surface_id=SYSTEM_ROOT_SURFACE_ID,
            label="Compendium",
            route=SYSTEM_ROOT_ROUTE,
            root_surface_id=SYSTEM_ROOT_SURFACE_ID,
            surface_kind="system_workspace",
            page_owner="system",
            default_surface=True,
        ),
        *network_root_entry,
        # The two roots the 2026-08-21 shell reorganization added. GADGETS is the
        # launcher page the rail's per-app / per-instrument items moved to; PROFILE is
        # the identity surface anchored at the foot of the rail. Roots, deliberately:
        # the operator's depiction names the activity bar's five entries as the
        # portal's top-level axes, superseding the 2026-06-05 three-root pin.
        PortalSurfaceCatalogEntry(
            surface_id=GADGETS_ROOT_SURFACE_ID,
            label="Gadgets",
            route=GADGETS_ROOT_ROUTE,
            root_surface_id=GADGETS_ROOT_SURFACE_ID,
            surface_kind="gadgets_root",
            page_owner="gadgets",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=PROFILE_ROOT_SURFACE_ID,
            label="Profile",
            route=PROFILE_ROOT_ROUTE,
            root_surface_id=PROFILE_ROOT_SURFACE_ID,
            surface_kind="profile_root",
            page_owner="profile",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_ROOT_SURFACE_ID,
            label="Utilities",
            route=UTILITIES_ROOT_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_root",
            page_owner="utilities",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_TOOL_EXPOSURE_SURFACE_ID,
            label="Tool Exposure",
            route=UTILITIES_TOOL_EXPOSURE_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_tool_exposure",
            page_owner="utilities",
        ),
        # Phase 14b: four dedicated Utilities surfaces. The legacy
        # tool-exposure entry above remains registered for one transition
        # cycle so
        # external bookmarks resolve via a 302 redirect at the HTTP layer.
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_EXTENSIONS_SURFACE_ID,
            label="Extensions",
            route=UTILITIES_EXTENSIONS_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_extensions",
            page_owner="utilities",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_GRANTEE_PROFILE_SURFACE_ID,
            label="Grantee Profile",
            route=UTILITIES_GRANTEE_PROFILE_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_grantee_profile",
            page_owner="utilities",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_TOOLS_SURFACE_ID,
            label="Tools",
            route=UTILITIES_TOOLS_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_tools",
            page_owner="utilities",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_PERIPHERALS_SURFACE_ID,
            label="Peripherals",
            route=UTILITIES_PERIPHERALS_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_peripherals",
            page_owner="utilities",
        ),
        # What this instance HOLDS on behalf of an alias: service keys, the AWS
        # identities behind the FND service module, and whether a payment instrument
        # is on file. A VIEW, never a write path -- minting and rotation keep their
        # own operator-gated routes.
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_WALLET_SURFACE_ID,
            label="Key Pass Wallet",
            route=UTILITIES_WALLET_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_wallet",
            page_owner="utilities",
        ),
        # The seams this instance has FILLED. Beside Tools rather than under it: a
        # tool is offered to a person and a binding is not offered to anyone -- it
        # acts for a farm it names, so what an operator needs to see is not whether
        # it is exposed but whether it is PERMITTED.
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_PORTS_SURFACE_ID,
            label="Ports",
            route=UTILITIES_PORTS_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_ports",
            page_owner="utilities",
        ),
        *network_tab_entries,
        # The HOLDINGS the Utilities page manages (convention section 3).
        # Tools/Peripherals above are POSTURE views; these are a manager for what
        # the instance holds. "Published" is the operator's Resource Management
        # tab — the enforced publication surface, and the only publish path.
        # Apps replaced the Tool Libraries / View Packages / Datum Packages stub
        # shelves (TASK-2026-08-14-002 Phase 1): a package already bundles tools,
        # provisioning and declared writes, so it is the one holding that existed.
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_APPS_SURFACE_ID,
            label="Apps",
            route=UTILITIES_APPS_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_apps",
            page_owner="utilities",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_CONTRACTS_SURFACE_ID,
            label="Held Contracts",
            route=UTILITIES_CONTRACTS_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_contracts",
            page_owner="utilities",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=UTILITIES_PUBLISHED_SURFACE_ID,
            label="Resource Management",
            route=UTILITIES_PUBLISHED_ROUTE,
            root_surface_id=UTILITIES_ROOT_SURFACE_ID,
            surface_kind="utilities_published",
            page_owner="utilities",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=WORKBENCH_UI_TOOL_SURFACE_ID,
            label="Workbench UI",
            route=WORKBENCH_UI_TOOL_ROUTE,
            root_surface_id=SYSTEM_ROOT_SURFACE_ID,
            surface_kind="tool_surface",
            page_owner="system",
            tool_id="workbench_ui",
        ),
        PortalSurfaceCatalogEntry(
            surface_id=AGRO_ERP_TOOL_SURFACE_ID,
            label="Agro ERP Workbench",
            route=AGRO_ERP_TOOL_ROUTE,
            root_surface_id=SYSTEM_ROOT_SURFACE_ID,
            surface_kind="tool_surface",
            page_owner="system",
            tool_id="agro_erp",
        ),
    )


def build_portal_tool_registry_entries() -> tuple[PortalToolRegistryEntry, ...]:
    from .shell import PortalToolRegistryEntry  # lazy to break import cycle
    return (
        PortalToolRegistryEntry(
            tool_id="agro_erp",
            label="Agro ERP Workbench",
            surface_id=AGRO_ERP_TOOL_SURFACE_ID,
            entrypoint_id=AGRO_ERP_TOOL_ENTRYPOINT_ID,
            route=AGRO_ERP_TOOL_ROUTE,
            read_write_posture="write",
            required_capabilities=("datum_recognition",),
            default_workbench_visible=True,
            # Plain datum-workbench surface (no spatial projection). Eligible
            # only for documents whose archetype is the agro_erp taxonomy row,
            # so samras_family documents don't accidentally pick up
            # agro_erp in the palette. See
            # docs/contracts/agro_erp_workbench_contract.md.
            applies_to_archetype=("agro_erp_taxonomy_row",),
            summary="Agro ERP taxonomy and source-document workbench (MOS-backed).",
        ),
        PortalToolRegistryEntry(
            tool_id="workbench_ui",
            label="Workbench UI",
            surface_id=WORKBENCH_UI_TOOL_SURFACE_ID,
            entrypoint_id=WORKBENCH_UI_TOOL_ENTRYPOINT_ID,
            route=WORKBENCH_UI_TOOL_ROUTE,
            read_write_posture="read-only",
            required_capabilities=("datum_recognition",),
            default_workbench_visible=True,
            # Workbench UI is the universal datum grid; appears in the palette
            # for both sandbox-source and system-anthology documents.
            applies_to_source_kind=("sandbox_source", "system_anthology"),
            summary="Read-only SQL datum grid with additive directive-overlay inspection.",
        ),
        # portal-tool-overlay-restructure: the 7 operator-facing legacy operator
        # extension tools (ext_aws_email / ext_analytics / ext_newsletter /
        # ext_paypal / ext_connect / ext_grantee_profile / ext_resources) were
        # dissolved. Their public /__fnd/* ingest + admin routes and the
        # _build_* payload builders they used remain; only the portal-shell
        # extension surface + renderers were removed.
    )


def resolve_portal_surface(
    surface_id: object, *, network_enabled: bool = True
) -> PortalSurfaceCatalogEntry | None:
    """The catalog entry for ``surface_id``, as this instance's catalog holds it.

    ``network_enabled`` must be threaded from the instance's config. It defaults to
    True to match ``build_portal_surface_catalog``, but the default is the one thing
    a caller resolving a REQUEST must not take: leaving it out builds the catalog
    the flag was set to prevent, so ``network.root`` resolves — launchable and
    allowed — on an instance that turned the network module off. The catalog builder
    gates the surface and the entries above say a sub-surface that survived the flag
    would be a side door; a resolver that rebuilds the catalog with the flag on is
    that same side door, reached from the other end.
    """
    normalized_surface_id = as_text(surface_id)
    for entry in build_portal_surface_catalog(network_enabled=network_enabled):
        if entry.surface_id == normalized_surface_id:
            return entry
    return None


def resolve_portal_tool_registry_entry(tool_id: object = "", *, surface_id: object = "") -> PortalToolRegistryEntry | None:
    normalized_tool_id = as_text(tool_id)
    normalized_surface_id = as_text(surface_id)
    for entry in build_portal_tool_registry_entries():
        if normalized_tool_id and entry.tool_id == normalized_tool_id:
            return entry
        if normalized_surface_id and entry.surface_id == normalized_surface_id:
            return entry
    return None


def canonical_route_for_surface(surface_id: object) -> str:
    entry = resolve_portal_surface(surface_id)
    return entry.route if entry is not None else SYSTEM_ROOT_ROUTE


def surface_root_id(surface_id: object) -> str:
    entry = resolve_portal_surface(surface_id)
    return entry.root_surface_id if entry is not None else SYSTEM_ROOT_SURFACE_ID


def is_tool_surface(surface_id: object) -> bool:
    return as_text(surface_id) in TOOL_SURFACE_IDS


def requires_shell_state_machine(surface_id: object) -> bool:
    return as_text(surface_id) in REDUCER_OWNED_SURFACE_IDS
