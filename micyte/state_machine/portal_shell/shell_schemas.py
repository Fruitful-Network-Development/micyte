"""Portal shell schema identifiers, surface IDs, routes, entrypoints, and constants."""

from __future__ import annotations

from micyte.core.instances import prettify_token

PORTAL_SHELL_REQUEST_SCHEMA = "mycite.v2.portal.shell.request.v1"
PORTAL_SHELL_STATE_SCHEMA = "mycite.v2.portal.shell.state.v1"
PORTAL_SHELL_COMPOSITION_SCHEMA = "mycite.v2.portal.shell.composition.v1"
PORTAL_SHELL_REGION_ACTIVITY_BAR_SCHEMA = "mycite.v2.portal.shell.region.activity_bar.v1"
# The instance switcher pinned to the foot of the activity bar: which MiCyte
# portal the operator is viewing as, and which others they may switch to.
PORTAL_SHELL_ACTIVITY_FOOTER_SCHEMA = "mycite.v2.portal.shell.activity_footer.v1"
PORTAL_SHELL_REGION_CONTROL_PANEL_SCHEMA = "mycite.v2.portal.shell.region.control_panel.v1"
PORTAL_SHELL_REGION_WORKBENCH_SCHEMA = "mycite.v2.portal.shell.region.workbench.v1"
# (The visualization_panel and interface_panel regions were retired — tools render
# in the menubar-search → full-screen overlay; their schema constants are gone.)
PORTAL_SURFACE_CATALOG_ENTRY_SCHEMA = "mycite.v2.portal.surface_catalog.entry.v1"
PORTAL_TOOL_REGISTRY_ENTRY_SCHEMA = "mycite.v2.portal.tool_registry.entry.v1"

SYSTEM_ROOT_SURFACE_ID = "system.root"
NETWORK_ROOT_SURFACE_ID = "network.root"
UTILITIES_ROOT_SURFACE_ID = "utilities.root"
UTILITIES_TOOL_EXPOSURE_SURFACE_ID = "utilities.tool_exposure"
# Phase 14b: replace the single mixed-purpose tool-exposure surface
# (which conflated extensions + tools + grantee profile + workbench UI)
# with four dedicated surfaces. The old IDs above stay registered for
# one transition cycle so external bookmarks still resolve via a 302
# redirect; new operator nav points at these.
UTILITIES_EXTENSIONS_SURFACE_ID = "utilities.extensions"
UTILITIES_GRANTEE_PROFILE_SURFACE_ID = "utilities.grantee_profile"
UTILITIES_TOOLS_SURFACE_ID = "utilities.tools"
UTILITIES_PERIPHERALS_SURFACE_ID = "utilities.peripherals"

WORKBENCH_UI_TOOL_SURFACE_ID = "system.tools.workbench_ui"
TRAPP_FAMILY_FARM_TOOL_SURFACE_ID = "system.tools.trapp_family_farm"

# Canonical sandbox tokens (underscore form per
# docs/contracts/datum_document_naming_taxonomy.md §"URL Slug vs
# Sandbox Token"). These are the only authoritative spellings —
# downstream code must import these constants rather than re-literal
# the strings.
WORKBENCH_UI_SANDBOX_TOKEN = "system"  # Workbench-UI is a system-sandbox reflective view
TRAPP_FAMILY_FARM_SANDBOX_TOKEN = "trapp_family_farm"
WOLF_FAMILY_SUSTAINABLE_FARM_SANDBOX_TOKEN = "wolf_family_sustainable_farm"  # onboarded farm (TASK-2026-07-10-008)
REGISTRAR_SANDBOX_TOKEN = "registrar"  # canonical identity/entity/geo sandbox (formerly mycelium_network; TASK-2026-07-01-001)
TAXONOMY_SANDBOX_TOKEN = "taxonomy"  # biological txa taxonomy: agro_erp txa vocab + common_name/icon_ref enrichment

def sandbox_display_name(token: str) -> str:
    """Return the human-readable label for a sandbox token.

    There used to be a SANDBOX_DISPLAY_NAMES override map consulted first, which
    doubled as the picker's allowlist — but every one of its five labels was
    byte-identical to the title-case fallback beneath it, so it only ever added
    two farms to the code that did not need to be there. Which sandboxes are
    *offered* is now discovered from the store (app.py::_sandbox_picker_options);
    retired sandboxes cannot reappear because they were purged from it.

    Rendering is delegated to prettify_token, whose word map covers the cases
    title-casing gets wrong ("Fnd Ebi" -> "FND EBI"). That map is about words,
    not sandboxes: onboarding a farm must never require an entry in it.
    """
    if not token:
        return ""
    return prettify_token(token)


PORTAL_SHELL_ENTRYPOINT_ID = "portal.shell"
WORKBENCH_UI_TOOL_ENTRYPOINT_ID = "portal.system.tools.workbench_ui"
TRAPP_FAMILY_FARM_TOOL_ENTRYPOINT_ID = "portal.system.tools.trapp_family_farm"

SYSTEM_ROOT_ROUTE = "/portal/system"
NETWORK_ROOT_ROUTE = "/portal/network"
UTILITIES_ROOT_ROUTE = "/portal/utilities"
UTILITIES_TOOL_EXPOSURE_ROUTE = "/portal/utilities/tool-exposure"
# Phase 14b: per-surface canonical routes.
UTILITIES_EXTENSIONS_ROUTE = "/portal/utilities/extensions"
UTILITIES_GRANTEE_PROFILE_ROUTE = "/portal/utilities/grantee-profile"
UTILITIES_TOOLS_ROUTE = "/portal/utilities/tools"
UTILITIES_PERIPHERALS_ROUTE = "/portal/utilities/peripherals"

WORKBENCH_UI_TOOL_ROUTE = "/portal/system/tools/workbench-ui"
TRAPP_FAMILY_FARM_TOOL_ROUTE = "/portal/system/tools/trapp-family-farm"

SYSTEM_ANCHOR_FILE_KEY = "anthology"
TOOL_ANCHOR_FILE_KEY = "anchor"
SYSTEM_ACTIVITY_FILE_KEY = "activity"
SYSTEM_PROFILE_BASICS_FILE_KEY = "profile_basics"
SYSTEM_SANDBOX_QUERY_FILE_TOKEN = "sandbox"

PORTAL_SCOPE_DEFAULT_ID = "fnd"
SURFACE_POSTURE_INTERFACE_PANEL_PRIMARY = "interface_panel_primary"
SURFACE_POSTURE_PALETTE_TARGET = "palette_target"
TOOL_KIND_GENERAL = "general_tool"
TOOL_KIND_SERVICE = "service_tool"
TOOL_KIND_HOST_ALIAS = "host_alias_tool"

# Document-archetype tokens used by PortalToolRegistryEntry.applies_to_archetype
# and by recognize_applicable_tools() to filter the palette. Values are lowercase
# slugs so they normalize consistently with AuthoritativeDatumDocument.source_kind.
# See portal_tool_surface_contract.md.
ARCHETYPE_SAMRAS_FAMILY = "samras_family"
ARCHETYPE_MSS_DOC = "mss_doc"
ARCHETYPE_HYPHAE_RUDI = "hyphae_rudi"

FOCUS_LEVEL_SANDBOX = "sandbox"
FOCUS_LEVEL_FILE = "file"
FOCUS_LEVEL_DATUM = "datum"
FOCUS_LEVEL_OBJECT = "object"
FOCUS_LEVELS = (
    FOCUS_LEVEL_SANDBOX,
    FOCUS_LEVEL_FILE,
    FOCUS_LEVEL_DATUM,
    FOCUS_LEVEL_OBJECT,
)
FOCUS_LEVEL_INDEX = {level: index for index, level in enumerate(FOCUS_LEVELS)}

VERB_NAVIGATE = "navigate"
VERB_INVESTIGATE = "investigate"
VERB_MEDIATE = "mediate"
VERB_MANIPULATE = "manipulate"
PORTAL_SHELL_VERBS = (
    VERB_NAVIGATE,
    VERB_INVESTIGATE,
    VERB_MEDIATE,
    VERB_MANIPULATE,
)

TRANSITION_ENTER_SURFACE = "enter_surface"
TRANSITION_FOCUS_SANDBOX = "focus_sandbox"
TRANSITION_FOCUS_FILE = "focus_file"
TRANSITION_FOCUS_DATUM = "focus_datum"
TRANSITION_FOCUS_OBJECT = "focus_object"
TRANSITION_BACK_OUT = "back_out"
TRANSITION_SET_VERB = "set_verb"
# Phase 12c (drift remediation): TRANSITION_OPEN_INTERFACE_PANEL and
# TRANSITION_CLOSE_INTERFACE_PANEL removed. The interface panel is hidden
# unconditionally since Phase 3d; toggling its open/closed chrome flag had
# no observable effect. The dispatch arms were also removed from
# reduce_portal_shell_state in shell.py.
PORTAL_SHELL_TRANSITIONS = (
    TRANSITION_ENTER_SURFACE,
    TRANSITION_FOCUS_SANDBOX,
    TRANSITION_FOCUS_FILE,
    TRANSITION_FOCUS_DATUM,
    TRANSITION_FOCUS_OBJECT,
    TRANSITION_BACK_OUT,
    TRANSITION_SET_VERB,
)

ROOT_SURFACE_IDS = frozenset(
    {
        SYSTEM_ROOT_SURFACE_ID,
        NETWORK_ROOT_SURFACE_ID,
        UTILITIES_ROOT_SURFACE_ID,
    }
)
TOOL_SURFACE_IDS = frozenset(
    {
        WORKBENCH_UI_TOOL_SURFACE_ID,
        TRAPP_FAMILY_FARM_TOOL_SURFACE_ID,
    }
)
SYSTEM_SURFACE_IDS = frozenset({SYSTEM_ROOT_SURFACE_ID, *TOOL_SURFACE_IDS})
NETWORK_SURFACE_IDS = frozenset({NETWORK_ROOT_SURFACE_ID})
UTILITIES_SURFACE_IDS = frozenset(
    {
        UTILITIES_ROOT_SURFACE_ID,
        UTILITIES_TOOL_EXPOSURE_SURFACE_ID,
        UTILITIES_EXTENSIONS_SURFACE_ID,
        UTILITIES_GRANTEE_PROFILE_SURFACE_ID,
        UTILITIES_TOOLS_SURFACE_ID,
        UTILITIES_PERIPHERALS_SURFACE_ID,
    }
)
# Phase A (function-forward refactor): the focus-path reducer is being
# retired. system.root went query-native in A1; cts_gis (A2) renders from
# tool_state, not the reducer's focus_path, so it is query-native too. No
# surface is reducer-owned now — the active state machine (transitions /
# reduce_portal_shell_state / activity dispatch bodies) is dead and is deleted
# in A3. (grantee_legacy was already retired from the surface catalog.)
REDUCER_OWNED_SURFACE_IDS: frozenset[str] = frozenset()
