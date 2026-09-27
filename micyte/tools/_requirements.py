"""What kind of instance a tool belongs to, stated once.

A tool declares ``requires`` so the rail and the menubar palette can ask whether THIS
instance can actually use it. Most tools fall into a small number of groups that need the
same thing, and writing the same requirement out twenty times is twenty things to keep in
step — so each group is one constant here and every member of it references that constant.

The alternative was a central table mapping tool ids to groups. That is the list-nothing-
maintains shape: a tool added tomorrow is absent from it and silently becomes "generic",
which is exactly the failure being fixed. A tool naming its own group cannot be forgotten,
because the tool is the thing being written.

## Why a DOCUMENT name and not an archetype

Both would work, and the document name is far cheaper: the instance's document names are one
indexed query, while its archetypes are a fold over every row it holds. This runs on the
shell request that paints the rail, so it is the difference between a lookup and a scan.

The document names chosen are the ones that DEFINE the kind of instance rather than merely
appear in it: a farm is the thing with a ``farm_profile``, the registrar's operator is the
thing with a ``legal_entity``. A tool wanting something narrower says so itself.
"""

from __future__ import annotations

from micyte.core.instance_baseline import CONTACT_FIELDS as _CONTACT_FIELDS
from micyte.ports.tool_package import DocumentRequirement, ToolRequirement

#: A FARM's surface. `farm_profile` is the farm's identity filament — the document that
#: makes a sandbox a farm rather than a sandbox with crops mentioned in it.
FARM = ToolRequirement(
    documents=(
        DocumentRequirement(
            name="farm_profile",
            archetype="farm_profile_identity",
            why="the farm whose ground, plots and books this tool works on",
        ),
    )
)

#: The REGISTRAR operator's surface — browsing or editing the network's own directory.
#: `legal_entity` is the registrar's roster of parties, held by the operator instance and
#: nobody else. A farm or a handyman reading its own portal has no business here, and before
#: this these tools were offered on every instance's search.
REGISTRAR = ToolRequirement(
    documents=(
        DocumentRequirement(
            name="legal_entity",
            archetype="legal_entity_profile",
            why="the network directory this tool browses or edits",
        ),
    )
)

#: An instance that BOOKS WORK: a job log to write into and the people to book it for.
#: Named for what it IS (a CRM's floor), not for the vertical that first needed it —
#: renamed from HANDYMAN in TASK-2026-08-14-002 Phase 3 for the same reason the hub was.
CRM = ToolRequirement(
    documents=(
        DocumentRequirement(
            name="job_log", archetype="job_event",
            why="the work this instance books"),
        DocumentRequirement(
            name="contacts", archetype="natural_entity_profile",
            why="the people it books work for"),
    )
)

#: An instance that KEEPS TIME-STAMPED RECORDS — satisfied by ANY ONE of these, not all.
#:
#: The general calendar reads every document whose archetype classes under `class_log`, so
#: it is meaningful wherever there is something to show. Declaring nothing said "everywhere",
#: and it landed on the registrar's rail beside the network's own calendar and on a farm's
#: rail with nothing to draw — the two-Calendars defect that scoping was supposed to end,
#: pointing the other way.
#:
#: This IS a census and it WILL go stale — a new kind of log added tomorrow is absent from
#: it, which is the failure mode this module's header warns about. It is here anyway because
#: the honest question ("does this instance hold a `class_log` document") cannot be asked
#: cheaply: `documents` carries no archetype column, so answering it means folding every row
#: the instance holds, on the request that paints the rail. The names are one indexed query.
#:
#: `test_calendar_scope_covers_every_live_log` is what catches the staleness: it asserts that
#: every sandbox live-holding a `class_log`-classed document satisfies this requirement. When
#: it fails, the new log's name belongs here — the test is the maintenance, not a promise
#: that maintenance is unnecessary.
ANY_LOG = ToolRequirement(
    documents_any=(
        DocumentRequirement(
            name="job_log", archetype="job_event",
            why="work this instance has booked"),
        # The canvassing log (2026-09-10): a knock is a dated event, and an instance that
        # has walked a street and booked nothing yet still has a calendar's worth of days.
        DocumentRequirement(
            name="canvass_log", archetype="canvass_visit",
            why="the doors this instance has knocked, by day"),
        DocumentRequirement(
            name="hc_log", archetype="event_log_entry",
            why="the network's own dated record"),
        DocumentRequirement(
            name="lc_log", archetype="event_log_entry",
            why="the network's own dated record"),
        DocumentRequirement(
            name="qc_log", archetype="event_log_entry",
            why="the network's own dated record"),
        DocumentRequirement(
            name="system_log", archetype="event_log_entry",
            why="what the instance records about itself"),
        DocumentRequirement(
            name="invoice", archetype="invoice",
            why="money owed or paid, which happens on a date"),
        DocumentRequirement(
            name="invoices", archetype="invoice",
            why="money owed or paid, which happens on a date — Brevat's ledger name"),
        DocumentRequirement(
            name="sales", archetype="invoice",
            why="a sale happens on a date — Brevat's ledger name"),
        # The stock log (2026-09-12): a delivery, a sale and a loss are each a dated
        # event, and a seller's week is largely made of them. An instance whose only log
        # is this one still has a calendar's worth of days, which is what this list
        # decides — the tripwire named it the moment the first one landed live.
        DocumentRequirement(
            name="stock_log", archetype="stock_entry",
            why="what came in and what went out, each on a day"),
    )
)

#: The fields a CONTACT tool writes, resolved through the anchor decoder ring.
#:
#: A document requirement asks whether the instance holds the right file; this asks whether
#: its anchor can express what the tool puts in it. Measured: `address("farm", f)` raises for
#: `ruiqi_id`, `email`, `sosvid` and `website` — so a farm holding `contacts` + `job_log`
#: passed the document gate, rendered the Contacts tab, and failed EVERY save.
#:
#: `nominal` is here because it RESOLVES in the registrar namespace, at the borrowed 3-1-31 —
#: which is why the check is `writable_fields` (defined plus borrowed) and not `fields`.
#: IMPORTED, not restated (2026-08-26). It now lives beside the baseline requirement for
#: `contacts` in `micyte.core.instance_baseline`, so the PROVISIONER's refusal and this
#: tool's refusal read the same list. They were two copies until TASK-2026-08-14-005
#: measured what that costs: the backfill created the document on anchors that could not
#: express it, because the provisioning side had no idea which fields a contact is made of.
CONTACT_FIELDS: tuple[str, ...] = _CONTACT_FIELDS

def structural_document_names(*, sandbox: str = "") -> frozenset[str]:
    """Every document name the CODE names — the set a rename may not touch.

    Filing a document into the local domain log renames it to its slot (``1-7``). That is
    safe for a document nothing looks up by name and fatal for one something does, so this
    is the question ``file_document`` asks first.

    DERIVED, never restated. Every entry comes from the declaration that already exists —
    the reserved anchor and local-domain names, the baseline floor, every registered tool's
    ``requires``, every package's own sandbox documents, the sources manifest and the record
    spec. A hand-kept list here would be a list nobody maintains, and the first tool to
    declare a new requirement would be the one whose document got renamed out from under it.

    ``sandbox`` adds what is structural about ONE sandbox: the archetype library's names ARE
    the registry's keys, so every document in it is structural.
    """
    from micyte.core import instance_baseline as _baseline
    from micyte.core.datum_ops.record_spec import SPEC_DOCUMENT
    from micyte.core.document_naming import (
        ANCHOR_DOCUMENT_NAMES,
        LOCAL_DOMAIN_DOCUMENT_NAMES,
    )
    from micyte.core.sources import MANIFEST_DOCUMENT

    from ._packages import catalogue
    from ._registry import TOOL_REGISTRY
    from .sources_manager import LEGACY_MANIFESTS

    names: set[str] = set(ANCHOR_DOCUMENT_NAMES)
    names.update(LOCAL_DOMAIN_DOCUMENT_NAMES)
    names.add(MANIFEST_DOCUMENT)
    names.update(LEGACY_MANIFESTS.values())
    names.add(SPEC_DOCUMENT)
    names.update(r.name for r in _baseline.BASELINE_DOCUMENTS)
    for tool in TOOL_REGISTRY.values():
        requires = getattr(tool, "requires", None)
        # ``documents_any`` counts too. It is a GATE concept — "any one of these" — but
        # every name in it is still a name a tool looks a document up by, and the fact
        # that holding one is optional says nothing about whether renaming it is safe.
        for field in ("documents", "documents_any"):
            for requirement in getattr(requires, field, ()) or ():
                names.add(str(getattr(requirement, "name", "")).strip())
    for package in catalogue():
        app_sandbox = getattr(package, "app_sandbox", None)
        for requirement in getattr(app_sandbox, "documents", ()) or ():
            names.add(str(getattr(requirement, "name", "")).strip())
    if str(sandbox or "").strip() == ARCHETYPE_SANDBOX:
        # The archetype LIBRARY is a registry keyed on the document name: `registry.get
        # ("text_note")` is how every viewscope, class fold and blank-instance mint finds
        # its shape. Renaming one to `1-7` would not break a lookup loudly — it would make
        # the archetype simply absent, and a document with no archetype draws as an
        # envelope saying nothing draws it.
        return frozenset(names | {"*"})
    return frozenset(name for name in names if name)


#: The sandbox whose every document name is a registry key.
ARCHETYPE_SANDBOX = "archetype"

__all__ = [
    "ANY_LOG",
    "ARCHETYPE_SANDBOX",
    "CONTACT_FIELDS",
    "CRM",
    "FARM",
    "REGISTRAR",
    "structural_document_names",
]
