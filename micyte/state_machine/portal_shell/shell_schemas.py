"""Portal shell schema identifiers, surface IDs, routes, entrypoints, and constants."""

from __future__ import annotations

import re as _re

from micyte.core.instances import prettify_token

PORTAL_SHELL_REQUEST_SCHEMA = "mycite.v2.portal.shell.request.v1"
PORTAL_SHELL_STATE_SCHEMA = "mycite.v2.portal.shell.state.v1"
PORTAL_SHELL_COMPOSITION_SCHEMA = "mycite.v2.portal.shell.composition.v1"
PORTAL_SHELL_REGION_ACTIVITY_BAR_SCHEMA = "mycite.v2.portal.shell.region.activity_bar.v1"
# The instance switcher pinned to the foot of the activity bar: which MiCyte
# portal the operator is viewing as, and which others they may switch to.
PORTAL_SHELL_ACTIVITY_FOOTER_SCHEMA = "mycite.v2.portal.shell.activity_footer.v1"
PORTAL_SHELL_REGION_WORKBENCH_SCHEMA = "mycite.v2.portal.shell.region.workbench.v1"
# (The visualization_panel, interface_panel and control_panel regions were retired —
# tools render in the WORKBENCH, and so does everything the control panel used to
# hold. Their schema constants are gone; the workbench is the only region with
# content, beside the activity bar that navigates to it.)
PORTAL_SURFACE_CATALOG_ENTRY_SCHEMA = "mycite.v2.portal.surface_catalog.entry.v1"
PORTAL_TOOL_REGISTRY_ENTRY_SCHEMA = "mycite.v2.portal.tool_registry.entry.v1"

SYSTEM_ROOT_SURFACE_ID = "system.root"
NETWORK_ROOT_SURFACE_ID = "network.root"
# The Network page is the msn_id BROWSER (convention section 4a) plus a P2P
# messaging centre (4b). The contract/event log that used to own /portal/network
# is a different concern — a system-log workspace — and keeps its surface id for
# bookmark stability while ceding the page's identity.
NETWORK_BROWSER_SURFACE_ID = "network.browser"
NETWORK_P2P_SURFACE_ID = "network.p2p"
# Operator directive 2026-08-17: the Network page IS the map, oriented like a consumer
# maps app, and three icons floating over it are the whole of its chrome — a gear to the
# settings page (what the Browser TAB was), a profile, and an inbox. These two are the
# destinations that did not exist yet. SUB-surfaces, like `network.browser`:
# `ROOT_SURFACE_IDS` is untouched and the 2026-06-05 no-new-root-surfaces ruling stands.
NETWORK_INBOX_SURFACE_ID = "network.inbox"
NETWORK_PROFILE_SURFACE_ID = "network.profile"
# Operator depiction 2026-08-21: the activity bar became exactly five fixed surfaces —
# Network, Compendium, Gadgets, Utilities, Profile — and these two are the roots that
# did not exist yet. GADGETS is the launcher page apps and instruments moved to when
# they left the rail; PROFILE is the identity surface (msn_profile + contact card +
# channel aliases + the instance switcher and sign-out). This deliberately supersedes
# the 2026-06-05 three-root ruling: the operator's new organization names five
# top-level axes, so `ROOT_SURFACE_IDS` grows with them.
GADGETS_ROOT_SURFACE_ID = "gadgets.root"
PROFILE_ROOT_SURFACE_ID = "profile.root"
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
UTILITIES_WALLET_SURFACE_ID = "utilities.wallet"
# The seams this instance has FILLED: which port, by which adapter, for which
# sandboxes, and whether the writes and calls it declares are actually permitted.
# Distinct from Tools (what the instance HOLDS and may render) because a binding is
# not offered to anyone -- it acts, unattended, for whichever farm it names.
UTILITIES_PORTS_SURFACE_ID = "utilities.ports"
# The HOLDINGS the Utilities page manages (convention section 3). This is a
# materialized management surface — what the instance HOLDS — and is deliberately
# not the tool overlay, which is where tools are RUN. Apps replaced the three
# stub shelves (Tool Libraries / View Packages / Datum Packages) in
# TASK-2026-08-14-002 Phase 1: an app is a package of tools with its provisioning
# and declared writes, so one shelf holds what three placeholders promised.
UTILITIES_APPS_SURFACE_ID = "utilities.apps"
UTILITIES_CONTRACTS_SURFACE_ID = "utilities.contracts"
# The operator's "Resource Management" tab: the ENFORCED publication surface.
UTILITIES_PUBLISHED_SURFACE_ID = "utilities.published"

WORKBENCH_UI_TOOL_SURFACE_ID = "system.tools.workbench_ui"
AGRO_ERP_TOOL_SURFACE_ID = "system.tools.agro_erp"

# Canonical sandbox tokens (underscore form per
# docs/contracts/datum_document_naming_taxonomy.md §"URL Slug vs
# Sandbox Token"). These are the only authoritative spellings —
# downstream code must import these constants rather than re-literal
# the strings.
WORKBENCH_UI_SANDBOX_TOKEN = "system"  # Workbench-UI is a system-sandbox reflective view
#: Every instance's core sandbox, per the naming contract — one per msn, all named this.
#: 2026-08-14: the three entity-named sandboxes below were renamed to it, so a name no
#: longer picks a tenant. An INSTANCE is an msn; the pair `(msn_id, sandbox)` is the address.
CORE_SANDBOX_TOKEN = "system"
#: The instance the legacy ``/portal/agro-erp`` route is pinned to. Named for the ROLE, not
#: the party: this constant used to be ``AGRO_ERP_LEGACY_MSN_ID``, which bound a family's
#: name to their network address inside the package the repo split publishes. The VALUE is
#: unchanged — only the symbol moved.
AGRO_ERP_LEGACY_MSN_ID = "3-2-3-17-77-2-6-3-1-6"

# Deleted 2026-08-22: RETIRED_SANDBOX_MSN_IDS and the three sandbox-token constants beside
# it. They read as a bookmark-redirect map — "kept only so a stored bookmark that still says
# one of them can be RECOGNISED and redirected" — which is why they looked load-bearing.
# Measured: NOTHING has ever read the dict, and two of the constants had no readers at all.
# They were a rename's residue describing an intention nobody implemented, and they cost
# three party names and two live addresses in a package headed for publication.
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
AGRO_ERP_TOOL_ENTRYPOINT_ID = "portal.system.tools.agro_erp"

# The Compendium — renamed from "System" (operator directive 2026-08-16) so the
# PAGE stops colliding with the `system` SANDBOX every instance carries. The
# surface id stays `system.root`: ids are code-facing and every canonical query,
# bundle rewrite and bookmark keys on them; the route and label are what an
# operator sees. The old route 302s here, query preserved.
SYSTEM_ROOT_ROUTE = "/portal/compendium"
LEGACY_SYSTEM_ROOT_ROUTE = "/portal/system"
NETWORK_ROOT_ROUTE = "/portal/network"
# Derived from the root rather than written out. Two reasons: a sub-route cannot
# drift from its parent, and the state-machine boundary test forbids a slash-
# delimited "network" path token anywhere in this package — a rule that exists to
# catch runtime/filesystem path leakage. Composing the route satisfies it without
# weakening the rule, which is the right way round.
NETWORK_BROWSER_ROUTE = f"{NETWORK_ROOT_ROUTE}/browser"
NETWORK_P2P_ROUTE = f"{NETWORK_ROOT_ROUTE}/p2p"
NETWORK_INBOX_ROUTE = f"{NETWORK_ROOT_ROUTE}/inbox"
NETWORK_PROFILE_ROUTE = f"{NETWORK_ROOT_ROUTE}/profile"
GADGETS_ROOT_ROUTE = "/portal/gadgets"
PROFILE_ROOT_ROUTE = "/portal/profile"
UTILITIES_ROOT_ROUTE = "/portal/utilities"
UTILITIES_TOOL_EXPOSURE_ROUTE = "/portal/utilities/tool-exposure"
# Phase 14b: per-surface canonical routes.
UTILITIES_EXTENSIONS_ROUTE = "/portal/utilities/extensions"
UTILITIES_GRANTEE_PROFILE_ROUTE = "/portal/utilities/grantee-profile"
UTILITIES_TOOLS_ROUTE = "/portal/utilities/tools"
UTILITIES_PERIPHERALS_ROUTE = "/portal/utilities/peripherals"
UTILITIES_WALLET_ROUTE = "/portal/utilities/wallet"
UTILITIES_PORTS_ROUTE = "/portal/utilities/ports"
UTILITIES_APPS_ROUTE = "/portal/utilities/apps"
UTILITIES_CONTRACTS_ROUTE = "/portal/utilities/contracts"
UTILITIES_PUBLISHED_ROUTE = "/portal/utilities/published"

WORKBENCH_UI_TOOL_ROUTE = "/portal/system/tools/workbench-ui"
AGRO_ERP_TOOL_ROUTE = "/portal/system/tools/agro-erp"

SYSTEM_ANCHOR_FILE_KEY = "anthology"
TOOL_ANCHOR_FILE_KEY = "anchor"
SYSTEM_ACTIVITY_FILE_KEY = "activity"
SYSTEM_PROFILE_BASICS_FILE_KEY = "profile_basics"
SYSTEM_SANDBOX_QUERY_FILE_TOKEN = "sandbox"

PORTAL_SCOPE_DEFAULT_ID = "fnd"
# SURFACE_POSTURE_* and TOOL_KIND_* were removed by the Phase 3 tool taxonomy along
# with the PortalToolRegistryEntry fields that were their only users. Both were
# validated and serialized and branched on by nothing: surface_posture had one
# permitted value, and every entry was TOOL_KIND_GENERAL. A vocabulary with no
# speakers reads like a distinction the system makes.

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
        GADGETS_ROOT_SURFACE_ID,
        PROFILE_ROOT_SURFACE_ID,
        UTILITIES_ROOT_SURFACE_ID,
    }
)
TOOL_SURFACE_IDS = frozenset(
    {
        WORKBENCH_UI_TOOL_SURFACE_ID,
        AGRO_ERP_TOOL_SURFACE_ID,
    }
)
SYSTEM_SURFACE_IDS = frozenset({SYSTEM_ROOT_SURFACE_ID, *TOOL_SURFACE_IDS})
NETWORK_SURFACE_IDS = frozenset(
    {
        NETWORK_ROOT_SURFACE_ID,
        NETWORK_BROWSER_SURFACE_ID,
        NETWORK_P2P_SURFACE_ID,
        NETWORK_INBOX_SURFACE_ID,
        NETWORK_PROFILE_SURFACE_ID,
    }
)
UTILITIES_SURFACE_IDS = frozenset(
    {
        UTILITIES_ROOT_SURFACE_ID,
        UTILITIES_TOOL_EXPOSURE_SURFACE_ID,
        UTILITIES_EXTENSIONS_SURFACE_ID,
        UTILITIES_GRANTEE_PROFILE_SURFACE_ID,
        UTILITIES_TOOLS_SURFACE_ID,
        UTILITIES_PERIPHERALS_SURFACE_ID,
        UTILITIES_WALLET_SURFACE_ID,
        UTILITIES_PORTS_SURFACE_ID,
        UTILITIES_APPS_SURFACE_ID,
        UTILITIES_CONTRACTS_SURFACE_ID,
        UTILITIES_PUBLISHED_SURFACE_ID,
    }
)
# Phase A (function-forward refactor): the focus-path reducer is being
# retired. system.root went query-native in A1; cts_gis (A2) renders from
# tool_state, not the reducer's focus_path, so it is query-native too. No
# surface is reducer-owned now — the active state machine (transitions /
# reduce_portal_shell_state / activity dispatch bodies) is dead and is deleted
# in A3. (grantee_legacy was already retired from the surface catalog.)
REDUCER_OWNED_SURFACE_IDS: frozenset[str] = frozenset()

#: The portal's icon sprite, served from the shared leaflet pool by `shared-assets.conf`
#: (which the portal vhost includes — a route on one vhost is a route on ONE vhost, and the
#: rail would draw nothing if it did not).
#:
#: Every symbol in it is `currentColor`, and every consumer themes it by setting `color`.
#: `fill` and `stroke` are IGNORED: an external `<use>` renders behind a shadow boundary the
#: host stylesheet cannot cross. Verified over HTTP, not assumed.
#:
#: Built by `scripts/build_portal_icon_sprite.py` from leaflets already in the pool.
PORTAL_ICON_SPRITE = "/assets/icons/0000-00-00.artifact-icon.mycite-ui.portal.svg"

# ---------------------------------------------------------------------------------------
# A RECORD TABLE'S OWN FILTER PARAMS                                          (2026-08-18)
#
# `micyte.tools._record_view` narrows a table with `<prefix>_q` (its search box) and
# `<prefix>_f_<column>` (one facet), namespaced by the table's own prefix so the tables
# sharing one surface query cannot read each other's filters.
#
# The two spellings live HERE, where the canonical query can also see them, and
# `_record_view` imports them. Restating them in the shell would have been the fourth
# place one rule is written down, and the one that drifts silently is always the filter:
# a dropped param leaves a table showing everything under a filter the operator believes
# is applied, and the export button beside it then takes the whole log out of the
# building.
#
# Measured before this was added: `canonical_query_for_surface_query` kept only the keys
# it names, so EVERY table filter — the jobs table's trade and month, the contacts
# table's, the ledgers' — was dropped on the round trip and did nothing at all.
RECORD_TABLE_SEARCH_SUFFIX = "_q"
RECORD_TABLE_FACET_INFIX = "_f_"

#: Which FACE of a table is drawn — its rows, or the same rows on a map. Same category as
#: the two above and namespaced the same way: it is one table's own presentation state, it
#: has to survive a round trip or the operator's chosen view snaps back on the next
#: transition, and it must not be a tool-invented shell key
#: (``forbidden_dependencies.md``: "tool-owned shell truth"). Adding it to the SHAPE rather
#: than to an allowlist is what keeps the next table that grows a map view from needing a
#: shell change of its own.
RECORD_TABLE_VIEW_SUFFIX = "_view"

#: WHICH ROW of a table is opened — the drill-in from a list to the one thing it lists.
#: Same category as the three above and namespaced the same way, and it is here rather
#: than in an allowlist for the reason ``_view`` is: the Clients table's drill-in into a
#: customer's jobs is the first, it will not be the last, and enumerating one table's
#: parameter in the shell is how the next one silently goes without.
#:
#: It has to survive the round trip or the drill-in is unreachable by reload or by link:
#: the canonical query keeps only the keys it names, so an unlisted spelling comes back
#: as the list every time and the ← back bar beside it would be the only state anything
#: could reach.
RECORD_TABLE_OPEN_SUFFIX = "_open"
#: WHICH ROW of a table is seeding a form somewhere on the same surface — the Contacts
#: table's *Schedule*, which opens `job_manager`'s own booking row prefilled from one
#: contact (`contacts_manager.SCHEDULE_PARAM`). Same category as the three above: it is one
#: table's own presentation state, it is namespaced by that table's prefix, and it has to
#: survive the round trip or the button would set a param the next response throws away and
#: the form would never open. Added to the SHAPE rather than to an allowlist, for the reason
#: stated below — the next table that grows a seeded form needs no shell change.
RECORD_TABLE_SEED_SUFFIX = "_seed"

#: The shell's own keys that happen to end in a record-table spelling. ``doc_view`` is the
#: open document's face (``scope`` / ``raw``), and the canonical query validates its VALUE
#: before keeping it. Without this exclusion the shape rule below would match it too and
#: copy it through unvalidated, so a nonsense ``doc_view`` would start surviving the round
#: trip — the shape widening quietly undoing a check that already existed.
_SHELL_KEYS_MATCHING_TABLE_SHAPE = frozenset({"doc_view"})

#: Bounded on purpose. The canonical query keeps only the keys it names, and this widens
#: that to a SHAPE rather than to anything at all: lowercase, a table prefix, and one of
#: the four spellings above. A pattern, because the alternative is enumerating every
#: table's prefix times every column it facets, which drifts the first time a facet is
#: added.
_RECORD_TABLE_FILTER = _re.compile(
    r"^[a-z][a-z0-9_]{0,31}(?:" + RECORD_TABLE_SEARCH_SUFFIX + r"|"
    + RECORD_TABLE_VIEW_SUFFIX + r"|"
    + RECORD_TABLE_OPEN_SUFFIX + r"|"
    + RECORD_TABLE_SEED_SUFFIX + r"|"
    + RECORD_TABLE_FACET_INFIX + r"[a-z0-9_]{1,40})$")


def is_record_table_filter_key(key: object) -> bool:
    """Is ``key`` one record table's own search, facet, view or drill-in parameter?"""
    """Is ``key`` one record table's own search, facet, view or seed parameter?"""
    token = key if isinstance(key, str) else ""
    if token in _SHELL_KEYS_MATCHING_TABLE_SHAPE:
        return False
    return bool(token) and bool(_RECORD_TABLE_FILTER.match(token))
