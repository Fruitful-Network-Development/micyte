"""Registry domain — the `msn_id` browser's engine.

The Network page browses msn nodes, and it sources that registry in one of two
**modes** (the design of record's cached-vs-linked axis):

``cached``
    Read the authority instance's *published still* — a `.mss` snapshot. No
    contract required, no authority database required, no live awareness.
``linked``
    Resolve live reachability through a held contract with the authority
    instance. Unlocks being findable, and tracking the shifting IP of a peer that
    has no DNS.

The mode is a property of the **browser**, layered over the datum-form axis
(``lv.``/``stl.``/``cptr.``) — it is not a fourth datum form. What varies is
which form the browser pulls and whether reachability is resolved dynamically.
"""

from .directory import (
    Node,
    Profile,
    ProfileSection,
    Region,
    RegistryDirectoryModel,
    build_directory_model,
    build_profile,
    decode_display_text,
    registrar_documents,
)
from .engine import (
    AUTHORITY_ROLE,
    EngineMode,
    RegistryDirectory,
    RegistrySource,
    authority_contract,
    directory_from_documents,
    directory_from_mss,
    resolve_engine_mode,
)
from .reachability import (
    Reachability,
    ReachabilityResolver,
    dns_reachability,
    is_live,
)

__all__ = [
    "AUTHORITY_ROLE",
    "EngineMode",
    "Node",
    "Profile",
    "ProfileSection",
    "Reachability",
    "ReachabilityResolver",
    "Region",
    "RegistryDirectory",
    "RegistryDirectoryModel",
    "RegistrySource",
    "authority_contract",
    "build_directory_model",
    "build_profile",
    "directory_from_documents",
    "directory_from_mss",
    "decode_display_text",
    "dns_reachability",
    "is_live",
    "registrar_documents",
    "resolve_engine_mode",
]
