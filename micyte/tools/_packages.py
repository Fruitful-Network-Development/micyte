"""The packages this build ships, and what installing one would provision.

The marketplace is a PORT (``micyte.ports.tool_package``). ``micyte.com`` is the authority
that publishes packages; this module is the **local** source — the catalogue of what the
build in front of you already contains. A package from here installs and runs; it is not
"listed" in the marketplace sense, because the marketplace's content is what the authority
vouches for and this build vouches only for itself.

That distinction is the operator's, and it is the seam the network fetch fills later: an
``official`` source implementing :class:`ToolPackageSource` returns packages fetched from
``micyte.com``, and everything downstream — the requirement preview, the install, the
ledger — is unchanged, because it already works from the port's types rather than from
where they came from.

## A package is declared, not derived

It would be possible to synthesise one package per registered tool. That would be worse:
``handyman_erp`` is three tools and four documents that only make sense together, and a
catalogue that offered them separately would let an operator install a jobs table with no
contact list to book against. A package is a decision about what ships together, so it is
written down.
"""

from __future__ import annotations

from typing import Any

from micyte.ports.external_call_policy import DeclaredCall
from micyte.ports.tool_package import (
    SOURCE_LOCAL,
    AppSandbox,
    DocumentRequirement,
    PortDeclaration,
    PortFill,
    PortFunction,
    ScopedFeature,
    ToolPackage,
    ToolPackageSource,
    installable_tools,
)

from ._registry import declared_writes, requirements_for


def _pinned(requirement: Any) -> Any:
    """The requirement with every document's ``archetype_hash`` filled from the lock.

    A tool names the archetype it needs; WHICH archetype — which hash — is a fact about
    the library this build was developed against, kept once in
    ``_archetypes.lock.json`` (D4). A tool that typed the hash itself would be a second
    statement of the same fact, and the `_package` docstring says what happens to those.
    A requirement that already carries a hash keeps it.
    """
    from dataclasses import replace

    from ._archetype_lock import archetype_hash

    def pin(documents: Any) -> tuple:
        return tuple(
            d if d.archetype_hash else replace(d, archetype_hash=archetype_hash(d.archetype))
            for d in documents)

    documents, documents_any = pin(requirement.documents), pin(requirement.documents_any)
    if documents == tuple(requirement.documents) and documents_any == tuple(requirement.documents_any):
        return requirement
    return replace(requirement, documents=documents, documents_any=documents_any)


def _package(package_id: str, *, version: str, label: str, summary: str,
             tools: tuple[str, ...], icon: str = "", **app_fields: Any) -> ToolPackage:
    """Build a package, taking `requires` and `writes` FROM THE TOOLS THEMSELVES.

    Never restated here. A package that carried its own copy of what its tools require
    would be a second statement of the same fact, free to drift from the first — the rule
    ``port_binding`` states about a binding's declared writes, and the reason
    ``_write_owners`` refuses a second declaration of one action.
    """
    requires_all = [_pinned(requirements_for(tool_id)) for tool_id in tools]
    writes: list = []
    for tool_id in tools:
        for write in declared_writes(tool_id):
            if write not in writes:
                writes.append(write)
    from micyte.ports.tool_package import ToolRequirement

    return ToolPackage(
        package_id=package_id, version=version, label=label, summary=summary,
        source=SOURCE_LOCAL, tools=tools, icon=icon, **app_fields,
        requires=ToolRequirement(
            sources=_unique(
                (s for r in requires_all for s in r.sources),
                key=lambda s: (s.sandbox, s.document)),
            documents=_unique(
                (d for r in requires_all for d in r.documents),
                key=lambda d: (d.name, d.archetype)),
            # A GATE concept, never provisioned, so a package does not carry one. Left out
            # rather than merged: "create one of these six" is not a decision an installer
            # may make, and a package quietly holding an any-of would invite exactly that.
            fields=_unique((f for r in requires_all for f in r.fields), key=lambda f: f),
        ),
        writes=tuple(writes),
    )


def _unique(items: Any, *, key: Any) -> tuple:
    """First-seen order, duplicates dropped.

    Deriving a package's requirements FROM ITS TOOLS is right and stays. What it means is
    that tools sharing a group constant — three of the four handyman tools reference the
    same `HANDYMAN` — contribute the same requirement three times, and concatenation kept
    every copy. Measured on the shipped package: seven document requirements for three
    documents.

    That reached the operator twice over. `unmet_requirements` filters by *not held*, so it
    dropped none of them; the install then built seven create requests and `create_document
    _rows` refused the fourth, leaving three documents created and nothing exposed. And the
    ledger printed the duplicates back: "Still needs: job_log, contacts, lcl, job_log, ...".

    Keyed on identity rather than on the object, because `why` differs between two
    declarations of one document — the ERP explains `job_log` differently from `job_manager`
    — and two spellings of the same requirement are still one requirement.
    """
    seen = set()
    out = []
    for item in items:
        token = key(item)
        if token in seen:
            continue
        seen.add(token)
        out.append(item)
    return tuple(out)


def catalogue() -> tuple[ToolPackage, ...]:
    """Every package this build offers.

    Built at call time rather than at import, because it reads the tool registry — and a
    module-level constant would freeze whatever happened to be imported first.
    """
    return (
        _package(
            # v2 of the package that shipped as `handyman_erp` 1.0.0 — the generalized CRM
            # lineage is Quiar, and the package offered to trade instances is
            # Quiar – Freelancer (TASK-2026-08-14-002 Phase 3). Nothing was installed
            # under the old id on any live instance, so the id changes with the version.
            "quiar",
            # 2.1.0: `rolodex` left the tool list when the tool was retired
            # (2026-08-16; a contacts document now opens as the same primitive in
            # the Compendium). The package_id is the identity install records key
            # on and it does not move with a version.
            #
            # 2.2.0: the hub opens on its DOMAIN. `lcl_editor` joins the tool list
            # because the tab is that tool, and `quiar_overview`/`project_manager`
            # stay in it although their tabs went — a package lists what an instance
            # may reach, and both are still reachable from the menubar.
            version="2.3.0",
            label="Quiar – Freelancer",
            summary=(
                "Book work, group it into projects, keep the people you book it for, and "
                "see the week. Nothing in it is trade-specific: a job's kind is a node the "
                "instance mints for itself."
            ),
            # `lcl_editor` is deliberately NOT here. A tool has ONE owning package —
            # `_tool_owners` refuses a second claim by name — and Oveure owns it. The
            # Domain TAB does not need ownership: a tab is a DECLARATION of a pane, built
            # server-side from that tool's own `panel_payload`, which is the same seam the
            # calendar tab and Oveure's inbox pane already use.
            tools=("quiar", "quiar_overview", "job_manager", "project_manager",
                   "contacts_manager", "calendar"),
            icon="quiar",
            hub_tool="quiar",
            app_sandbox=AppSandbox(
                namespace="registrar",
                why=(
                    "A booking instance's anchor is copied verbatim from the registrar's, "
                    "so its numbering IS the registrar's — installing this app records "
                    "that claim instead of a hand edit and a deploy."
                ),
                # The hub opens on its DOMAIN, and a node there can denote a document —
                # so the sandbox is seeded with the reserved `documents` branch beside the
                # operator's own tree rather than growing one on the first write.
            ),
            # Still no port declarations, and still honestly: no Quiar tab calls a port
            # yet. The email and hosting seams are declared with the first feature that
            # employs them, not before — a declared seam nothing fills is decoration.
            scoped_features=(
                ScopedFeature(
                    tool_id="calendar",
                    scope="app_sandbox",
                    why=(
                        "The hub's calendar tab is this instance's own schedule, pinned; "
                        "the standalone calendar tool is the cross-sandbox surface with "
                        "per-sandbox toggles."
                    ),
                ),
                ScopedFeature(
                    tool_id="contacts_manager",
                    scope="app_sandbox",
                    why=(
                        "The hub's Clients tab edits this sandbox's own contacts; "
                        "opening a contacts document in the Compendium is the same "
                        "primitive on that document's own books."
                    ),
                ),
            ),
        ),
        _package(
            # The generalized ERP lineage (TASK-2026-08-14-002 Phase 4). The specialized
            # package for farm instances — Brevat – Farmers, which absorbs the farm panes
            # and retires `agronomics` at live parity — is the Farmers phase's, not this
            # one's: this is generic Brevat, and its ledger tabs render their honest
            # empty/error states until the modern archetype-row ledger lands (see
            # `brevat.py`'s header for what Phase 4 verification found).
            "brevat",
            # 1.1.0 (2026-09-12): the Stock tab and its `stock_log` document — what came
            # in and what went out, and the on-hand figure summed from it.
            version="1.2.0",
            label="Brevat",
            summary=(
                "Products, supply, sales and the standing offer, for an instance that "
                "sells goods. The commerce seam is DECLARED here and bound — and "
                "granted — by the operator on Ports, never by installing."
            ),
            # The MODERN ledger (Farmers phase): installing provisions invoices/sales/
            # offering as archetype-row documents the three managers append to. The old
            # panes stay registered for the lifted farm tabs, outside this package.
            # `product_catalog` carries the `product_profiles` requirement, so
            # installing PROVISIONS the document its Products tab appends to.
            # Without it the tab is a screen that cannot be filled, which is the
            # state the farm instance was measured in on 2026-09-02.
            # `stock_log` joins 2026-09-12 (TASK-2026-09-12-001): a package provisions the
            # documents ITS TOOLS declare, so the Stock tab's log arrives with the app
            # rather than being minted by the first movement somebody tries to record.
            tools=("brevat", "product_catalog", "stock_log", "supply_ledger",
                   "sales_ledger", "offer_ledger"),
            icon="brevat",
            hub_tool="brevat",
            app_sandbox=AppSandbox(
                namespace="farm",
                why=(
                    "A goods-selling instance's anchor comes from the farm template "
                    "(`bootstrap_farm_sandbox`), whose numbering carries the fiat/price "
                    "babelette the ledger writes against — installing records that claim "
                    "instead of a hand edit and a deploy."
                ),
                # The app's own datum-doc default BEYOND what its tools require: the
                # planting book (supply-backed planting, batch re-point). The planting
                # tools are the lifted farm tabs — a LIBRARY, not package tools — so
                # their document cannot ride the tools-derived requirements; this seam
                # exists for exactly that ("defaults for datum docs").
                documents=(
                    DocumentRequirement(
                        name="plantings", archetype="planting",
                        why="supply batches committed to plots — the planting book "
                            "add_planting appends to"),
                ),
            ),
            # The app's ONE port, and the program's first real declaration: the
            # commerce_offering seam the Offering tab already consumes (catalog +
            # availability through `_offering`), with the payment egress named at the
            # grain an operator would withhold. Declared, never bound: filling it with
            # `DatumOfferingAdapter` (and granting the PayPal calls) is the operator's
            # decision on Ports.
            port_declarations=(
                PortDeclaration(
                    port_id="commerce_offering",
                    why=(
                        "what this instance offers, published and quotable; payment "
                        "capture rides PayPal when — and only when — an operator binds "
                        "and grants it"
                    ),
                    calls=(
                        DeclaredCall(service="paypal", operation="order.create"),
                        DeclaredCall(service="paypal", operation="order.capture"),
                    ),
                ),
            ),
        ),
        _grantor_package(),
        _oveure_package(),
        _enchir_package(),
        _pim_package(),
        _fnd_service_package(),
        _claude_package(),
    )


# --------------------------------------------------------------------------- #
# Extensions — packages that FILL a port rather than employ one
# --------------------------------------------------------------------------- #
#: The dotted path the host imports to fill `email_provider` with FND's own service.
#: Stated once, here, because an operator selecting an extension must never be in a
#: position to type an import path.
_FND_SERVICE_EMAIL_ADAPTER = (
    "fnd_app.packages.grantee_services.fnd_service.email.FndEmailAdapter"
)

#: The same, for `site_hosting`. A SECOND adapter on ONE extension: FND is the
#: intermediary for both the mail and the served tree, so the two fills carry the same
#: `service` token and an operator binding either is binding FND-as-intermediary.
_FND_SERVICE_SITE_ADAPTER = (
    "fnd_app.packages.grantee_services.fnd_service.site.FndSiteAdapter"
)

#: The external-call SERVICE token grants name for FND-as-intermediary. Deliberately NOT
#: `aws_ses`: FND relaying a client's mail and a client holding SES keys are the same port
#: filled two ways and are not the same disclosure, so one grant must never be the other.
FND_SERVICE = "fnd_service"


def _extension(package_id: str, *, version: str, label: str, summary: str,
               port_fills: tuple[PortFill, ...], icon: str = "") -> ToolPackage:
    """An extension: a package that installs no tools and fills a port.

    Built directly rather than through `_package`, which derives `requires` and `writes`
    FROM the tools — an extension has none, so that derivation would read an empty tuple
    and the helper's whole purpose would be doing nothing. A separate constructor also
    keeps the two kinds visibly different in this file, which is the point of the shelf.
    """
    return ToolPackage(
        package_id=package_id, version=version, label=label, summary=summary,
        source=SOURCE_LOCAL, tools=(), icon=icon, port_fills=port_fills,
    )


def _fnd_service_package() -> ToolPackage:
    """FND Service — the intermediary, and the program's first extension.

    The operator's depiction: FND holds the accounts (the AWS account, and later the
    analytics and payment wiring), a client instance holds none of them, and the seam
    between the two is a port an instance SELECTS rather than a route FND wrote for one
    purpose. This package is that seam's first filling.

    TWO fills. Email came first; `site_hosting` joined it 2026-08-26 when client
    authoring arrived, and it belongs on the SAME extension because it is the same
    intermediary: FND holds the mail account and FND serves the tree, and an instance
    holds neither. `sms_provider` still has no fill and stays a port type with no eligible
    extension — declaring one because SMS is coming would put a row on the Ports surface
    an operator could select and that would then do nothing.

    SIXTEEN functions, and the number is not an ambition — it is the two adapters' own
    authorized method lists, said out loud. Until 2026-08-29 this manifest declared SEVEN
    while `fnd_service/email.py` and `fnd_service/site.py` called `self._authorize(...)`
    for sixteen: the six mailbox-administration operations, and `analytics.read`,
    `content.replace` and `asset.upload`, were added to the code and granted BY HAND in
    `external_call_grants`, and were never written down here.

    That cost more than tidiness. `check_fnd_service_grants` — the tool whose entire job
    is telling an operator what to grant — asks a fill what it performs, so nine live,
    already-granted operations were invisible to it and an operator relying on it would
    never have learned they existed. An extension that under-declares its own adapter
    makes the permission surface lie by omission, which is the one failure the
    declare-then-bind-then-grant split exists to prevent.

    The paragraph this replaces said site hosting's three were "a PARTIAL fill and that
    is the point", because `content.replace` and `asset.upload` belonged to an iframe
    editor with a posture of its own. That was true when it was written and stopped being
    true on 2026-08-29, when `grant_site_content_editing.py` permitted both on every
    client's site binding and PIM's Site tab grew the controls that reach them. A
    declaration describes what something PERFORMS, so it may only be widened in that
    direction: what made this safe was a form posting to both, not a plan to build one.
    A fill may still honestly be partial — the rule stands, and `sms_provider` is the
    live example — but this one no longer is.

    ORDER IS LOAD-BEARING, so the two lists are sorted rather than appended to.
    `check_fnd_service_grants --print-grant` emits `operations` in declaration order and
    tells the operator to TRIM it, because "the ones that SEND are last on purpose". Each
    fill therefore reads: the READS first, then the writes that stay inside the client's
    own arrangements, then the ones that put words or bytes in front of somebody else.
    Cut the tail off either printed list and what remains is always the narrower grant;
    appending a new function without asking that question would silently make the advice
    wrong.
    """
    from micyte.ports.email_provider import (
        OPERATION_ALIAS_CREATE,
        OPERATION_ALIAS_LIST,
        OPERATION_ALIAS_REMOVE,
        OPERATION_FORWARDING_SET,
        OPERATION_IDENTITY_REMIND,
        OPERATION_IDENTITY_VERIFY_REQUEST,
        OPERATION_MAILBOX_LIST,
        OPERATION_MESSAGE_FETCH,
        OPERATION_MESSAGE_FORWARD,
        OPERATION_MESSAGE_SEND,
    )
    from micyte.ports.site_hosting import (
        OPERATION_ANALYTICS_READ,
        OPERATION_ARTICLE_PUBLISH,
        OPERATION_ARTICLE_RETIRE,
        OPERATION_ARTICLE_SEND,
        OPERATION_ASSET_SWAP,
        OPERATION_ASSET_UPLOAD,
        OPERATION_CONTENT_REPLACE,
        OPERATION_PAGE_LIST,
        OPERATION_PROFILE_EDIT,
        OPERATION_PROJECT_EXPORT,
    )

    return _extension(
        "fnd_service",
        # 1.2.0 for the nine functions this build declares that 1.1.0 did not. The
        # adapters did not change; what changed is that the manifest now says what they
        # do. An instance's `installed_packages` record still reads an older number and
        # that is CORRECT — the record is the audit fact of what an operator agreed to,
        # and the declaration is read from the catalogue (`_installed_declarations`).
        # 1.3.0 (2026-08-31): `asset.swap`. A declaration describes what something
        # PERFORMS and may only be widened in that direction — what makes this honest is
        # `FndSiteAdapter.swap_asset`, landing in the same commit.
        # 1.4.0 (2026-09-10): `profile.edit`, same rule — `FndSiteAdapter.edit_profile`
        # lands with it, for Enchir's project editor.
        # 1.5.0 (2026-09-11): `project.export` — `FndSiteAdapter.export_project`: a
        # project DOCUMENT's view written beside the site, the profile derived from it.
        # 1.6.0 (2026-09-13): `article.send` — `FndSiteAdapter.send_article`. The same
        # widening rule, on the one function of this port that leaves the building: an
        # operator who has already granted publishing is NOT thereby granting the mail,
        # because a version bump does not re-grant anything — the record of what they
        # agreed to is what `installed_packages` holds, and this has to be chosen.
        version="1.6.0",
        label="FND Service",
        summary=(
            "Connect this instance to what FND already runs for it: the mail — read "
            "what arrived, administer the addresses on its domains, answer from one of "
            "them, or hand a message to a person — and the served site, where pages can "
            "be read and edited, writing published, sent to the people who subscribed, "
            "or taken down, assets uploaded, and "
            "the month's traffic counted. FND holds the accounts; this instance holds "
            "no credential."
        ),
        icon="fnd_service",
        port_fills=(
            PortFill(
                port_id="email_provider",
                adapter_id=_FND_SERVICE_EMAIL_ADAPTER,
                service=FND_SERVICE,
                why=(
                    "FND already receives and sends this domain's mail, and holds the "
                    "addresses it is received at. Selecting this lets the instance work "
                    "with both directly instead of a person copying it across."
                ),
                functions=(
                    # ---- the READS: what exists, and what it says.
                    PortFunction(
                        operation=OPERATION_MAILBOX_LIST,
                        why="See what has arrived. Discloses who wrote, and when.",
                    ),
                    PortFunction(
                        operation=OPERATION_MESSAGE_FETCH,
                        why="Open one message. Discloses what they said.",
                    ),
                    PortFunction(
                        operation=OPERATION_ALIAS_LIST,
                        why=(
                            "See which addresses exist on this client's domains, where "
                            "each hands its mail on to, and how far each has got "
                            "through send-as confirmation. Discloses the shape of "
                            "somebody's mail and none of its contents. Withhold it and "
                            "PIM's Email tab has nothing to draw."
                        ),
                    ),
                    # ---- ADMINISTRATION: changes the client's own arrangements, and
                    # puts nothing in front of anybody else.
                    PortFunction(
                        operation=OPERATION_ALIAS_CREATE,
                        why=(
                            "Bring a new address into existence on a domain this client "
                            "owns. Withhold it and minting addresses stays the "
                            "operator's job, which is where it was before PIM."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_ALIAS_REMOVE,
                        why=(
                            "Take an address away. Separate from creating one because "
                            "an address that has been given out is on somebody's "
                            "letterhead, and removing it loses the mail already "
                            "addressed to it."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_FORWARDING_SET,
                        why=(
                            "Change where an existing address hands its mail on to. The "
                            "change a client asks for most often, and the one that "
                            "silently redirects correspondence when it is wrong — so it "
                            "is refusable on its own rather than folded into "
                            "`alias.create`."
                        ),
                    ),
                    # ---- the ones that reach a STRANGER. Last, so that trimming the
                    # printed grant from the end always narrows it.
                    PortFunction(
                        operation=OPERATION_MESSAGE_SEND,
                        why=(
                            "Send from this address, to whoever the caller names. The "
                            "only function a stranger ever sees."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_MESSAGE_FORWARD,
                        why=(
                            "Hand a message to an address configured in advance. "
                            "Separate from sending because handing work to the owner "
                            "and writing to anyone are different permissions."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_IDENTITY_VERIFY_REQUEST,
                        why=(
                            "Send the setup handoff to the personal address behind a "
                            "mailbox, so its owner can confirm they may send AS the "
                            "domained one. It SENDS MAIL to a person, which is why it "
                            "sits here rather than beside `alias.create`. Withhold it "
                            "and addresses can be made but never sent from."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_IDENTITY_REMIND,
                        why=(
                            "Nudge an owner who has not finished confirming. Also sends "
                            "mail, and separately refusable: an operator may want the "
                            "one-time handoff without a reminder cadence."
                        ),
                    ),
                ),
            ),
            PortFill(
                port_id="site_hosting",
                adapter_id=_FND_SERVICE_SITE_ADAPTER,
                service=FND_SERVICE,
                why=(
                    "FND already serves this domain's site and counts what visits it. "
                    "Selecting this lets the instance read, edit and publish to it "
                    "instead of an operator typing it into a dashboard on their behalf."
                ),
                functions=(
                    # ---- the READS.
                    PortFunction(
                        operation=OPERATION_PAGE_LIST,
                        why=(
                            "See which pages the site has and which pieces it carries. "
                            "Discloses the shape of somebody's site and nothing else."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_ANALYTICS_READ,
                        why=(
                            "A month of the site's traffic, counted. The only function "
                            "here that touches nobody's words and the only one an "
                            "unattended routine performs, so it is what an operator "
                            "grants a nightly refresh while every write below stays "
                            "withheld."
                        ),
                    ),
                    # ---- writes that CHANGE OR REMOVE what is already published.
                    PortFunction(
                        operation=OPERATION_CONTENT_REPLACE,
                        why=(
                            "Apply one {old, new} pair to the site's source: change the "
                            "words a stranger reads on a page that already exists. "
                            "Withhold it and a client can look at their own site and "
                            "not fix a typo in it."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_ARTICLE_RETIRE,
                        why=(
                            "Take one down. Separate from publishing because a mistaken "
                            "publish is embarrassing and a mistaken retire loses work, "
                            "and an operator may well permit one and not the other."
                        ),
                    ),
                    # ---- writes that put something NEW at a public address.
                    PortFunction(
                        operation=OPERATION_ARTICLE_PUBLISH,
                        why=(
                            "Put a piece of writing on the public internet under this "
                            "client's name, at a new address, with a tile pointing at "
                            "it. The function a stranger reads."
                        ),
                    ),
                    # ---- the write that leaves this building entirely.
                    PortFunction(
                        operation=OPERATION_ARTICLE_SEND,
                        why=(
                            "Put the same piece of writing in the inboxes of the people "
                            "who subscribed to this site. THE ONE FUNCTION HERE THAT "
                            "CANNOT BE UNDONE: a publish can be taken back down in a "
                            "minute and a send cannot be taken back at all. Withhold it "
                            "and the client writes for the web exactly as before; grant "
                            "it and they can mail everyone on their list without asking "
                            "anybody. The surface states the count before it sends."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_ASSET_SWAP,
                        why=(
                            "Point a picture on a page at a different file the site "
                            "already has. Its own permission because its fence is its "
                            "own: the target must be in the site's gallery, where a "
                            "content replacement could point an <img> anywhere. The "
                            "store has refused an off-gallery target since the legacy "
                            "design tab, and nothing could reach that check until this."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_ASSET_UPLOAD,
                        why=(
                            "Put new bytes at a public URL. Deliberately not the same "
                            "permission as replacing a word: an edit changes what the "
                            "site SAYS, an upload changes what it SERVES, and the "
                            "second is how a site comes to host a file nobody reviewed."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_PROFILE_EDIT,
                        why=(
                            "Rewrite a profile the pages are generated from — which "
                            "photograph stands for a project, the order and hiding of "
                            "the rest, its short and long description — and rebuild "
                            "them. Its own permission because one save reaches several "
                            "pages at once and can take a photograph off the site "
                            "without deleting it; every ref is fenced to the "
                            "profile's own gallery."
                        ),
                    ),
                    PortFunction(
                        operation=OPERATION_PROJECT_EXPORT,
                        why=(
                            "Write a project document's view beside the site's assets, "
                            "land any picture the site's pool lacks, and derive the "
                            "profile the pages are generated from — the instance's "
                            "books become the source and the leaflet a copy. Its own "
                            "permission because it lands files and rewrites a profile "
                            "in one act."
                        ),
                    ),
                ),
            ),
        ),
    )


def _claude_package() -> ToolPackage:
    """Claude — the `ai_provider` fill, and why the AI adapters became an extension.

    The adapter itself is not new; it has shipped since the Oveure phase and the ask relay
    already calls it. What was missing is the SAYING so: nothing declared that a thing
    existed which could fill `ai_provider`, so the Ports surface could show the port as
    declared-and-unfilled and offer no way to fill it.

    The key keeps its existing home (`private/utilities/tools/ai/<provider>.json`). An
    extension declares what it can do and what a call would disclose; where the credential
    lives is the host's decision and moving it would be a migration wearing a
    marketplace's clothes.
    """
    from micyte.ports.ai_provider import OPERATION_MESSAGES_CREATE

    return _extension(
        "claude",
        version="1.0.0",
        label="Claude",
        summary=(
            "Send text to Anthropic's models and read the reply. The key is yours and "
            "stays on this instance; what the call discloses is the text itself."
        ),
        icon="claude",
        port_fills=(
            PortFill(
                port_id="ai_provider",
                adapter_id="fnd_app.packages.peripherals.ai.anthropic_messages.AnthropicMessagesAdapter",
                # The SERVICE is the provider here, deliberately: a grant over Anthropic
                # is never a grant over OpenAI, which is why there is no umbrella "ai".
                service="anthropic",
                why=(
                    "A draft goes to the model and the reply comes back unsaved. "
                    "Writing it down stays a person's own act."
                ),
                functions=(
                    PortFunction(
                        operation=OPERATION_MESSAGES_CREATE,
                        why=(
                            "Send the turns and pay for the answer. What it discloses "
                            "is whatever text was in them."
                        ),
                    ),
                ),
            ),
        ),
    )


def _pim_package() -> ToolPackage:
    """PIM — Personal Information Manager. The CLIENT's app, on the client's instance.

    The operator's depiction, and the correction it makes to an easy misreading: the
    CHANNEL is where an alias manages the services they pay for and collects the API keys
    for them; the Use button binds a key to one of THEIR ports; and "thereafter the
    relationship a client has with their provider services is entirely facilitated through
    a new sandbox and application called PIM".

    So this is not the operator looking at a client. It is the client's own instance
    holding its own records, reaching FND's services through ports its own key permits —
    "enabled and permitted to use the ports like FND Domain port or FND payment hub".

    That is also why it does not contradict `grantee_dashboards_not_portals`. That rule
    governs surfaces on the FND portal that a grantee logs in to. A client with their own
    msn, their own portal and their own sandboxes is not that case: the data is theirs and
    it lives in their store, which is the isolation the operator asked for in the words
    "the sandbox isolated location".

    ## What it keeps, and where the data comes from

    Datum record documents in its own sandbox — analytics, contacts signed up from the
    website, newsletter drafts for subscribed contacts — updated from the FND module
    through a port, and read back as tables. Email is the same shape: AWS's view of an
    instance's users and their verification stages, fetched with the key and kept as
    records rather than proxied live.

    ## Why it declares a port and no tools for most of its tabs

    The port is the POINT: without one, PIM is a sandbox with nothing to fill it. It is
    declared and NOT bound — binding is the operator's act on Ports, with the grant a
    separate act after that, exactly as oveure's AI seam ships.

    The tabs are the honest part. Analytics, Contacts, Newsletters and Email have no
    tool behind them yet, so this package does not offer them; a package listing a tab
    that cannot open is the gear the glyph library rejected, one layer up. It serves
    `pim_overview` and nothing else. It also PROVISIONS a `contacts` document, which
    quiar's `contacts_manager` opens on although this package does not declare that tool —
    a package decides what is provisioned, while `applies_to_archetype` decides what
    opens.

    (Until 2026-08-24 this paragraph asserted that two of those tabs were already
    served — a survivor of the FIRST draft, which tried to borrow another lineage's
    contacts tool and the Compendium's artifacts shelf before `packages_by_tool`'s
    one-lineage rule made that impossible. The comment on `tools` below explains why
    the borrow was dropped; this prose was never updated to match, so it presented two
    of the four real tabs as done while the summary and the tuple both said zero were.
    Prose that disagrees with the tuple beside it is read first and believed longest.
    `TheDepictionMatchesTheDeclaration` in test_pim_package.py now checks the three
    against each other.)

    NOTHING HERE TOUCHES THE EXISTING DASHBOARD, or any mail or website behaviour. The
    operator has asked for the old dashboard to remain until they say the cutover is
    ready, and this package binds nothing, grants nothing and sends nothing.
    """
    return _package(
        "pim",
        version="0.1.0",
        label="PIM",
        summary=(
            "The client's own record of their provider-service relationship, held as "
            "datum documents in an isolated sandbox and fed through the ports their own "
            "service key permits. The home tab says what the sandbox keeps and whether "
            "the FND seam is bound and permitted; Design shows the client's own site and "
            "publishes their writing to it. Analytics, Contacts, Newsletters and Email "
            "are planned tabs with no tool behind them yet, so this package does not "
            "offer them."
        ),
        # ITS OWN tool, and only its own. The first draft borrowed `contacts_manager`
        # from quiar and `artifacts` from the Compendium's shelf. Both were wrong:
        # `packages_by_tool` raises on a shared claim because a tool belongs to exactly one
        # lineage, and the contract refuses a hub that "is not among the package's tools —
        # an app's hub is one of the things it installs, not a reference to somebody
        # else's". Semantically wrong too: quiar's contacts are a CRM's, PIM's are people
        # who signed up on a website. Same word, different record.
        tools=("pim_overview", "pim_design"),
        icon="folder",
        hub_tool="pim_overview",
        app_sandbox=AppSandbox(
            # The one record kind PIM can honestly OPEN today. This package does not
            # declare `contacts_manager` and cannot — it is quiar's, and a tool belongs to
            # exactly one lineage. It does not need to: a package does not decide what
            # OPENS, `applies_to_archetype` does, and that tool applies to
            # `natural_entity_profile`. So this needs the DOCUMENT and no new tool.
            #
            # The other three kinds `pim_overview` names have no archetype decided yet, and
            # the home tab now says so in those words rather than reporting them as
            # "waiting on the seam" — which was true, and was not the reason they cannot be
            # opened. Binding a port would not change it.
            documents=(
                DocumentRequirement(
                    name="contacts", archetype="natural_entity_profile",
                    why="people who signed up on the client's website — the client's own "
                        "record of them, in their own sandbox. NOT quiar's CRM contacts: "
                        "same archetype, different record"),
            ),
            # INHERIT — the one thing about PIM decided before it was designed. Oveure
            # shipped a static "system", the namespace of exactly ONE instance's core
            # anchor (FND's) and one with no lcl-node vocabulary, so its Domain tab could
            # never have minted on a farm or a client instance. A PIM sandbox is copied
            # from the instance's own core anchor the same way, so the same token would be
            # wrong in the same way — and PIM is meant to run on CLIENT instances, which
            # is precisely where that token fails.
            namespace="",
            why=(
                "a PIM sandbox's anchor is copied verbatim from the instance's own core "
                "anchor, so its namespace is INHERITED and resolved at install — never "
                "stated as a token that could disagree with the copy"
            ),
        ),
        port_declarations=(
            PortDeclaration(
                port_id="email_provider",
                why=(
                    "the FND module seam: an instance's own mail, and AWS's view of its "
                    "users and their verification stages, fetched with the service key "
                    "the channel minted and kept as records. DECLARED, not bound — "
                    "binding is the operator's act on Ports and the grant a separate one "
                    "after it, so this ships able to do nothing"
                ),
                # OPERATIONS, not calls: PIM employs "list what arrived" and "open one",
                # and WHICH extension carries that — FND relaying it, or a direct SES
                # adapter — is the operator's choice on Ports, made after this manifest
                # was written. Naming a vendor here would pin PIM to one extension and
                # quietly stop matching the moment somebody chose another.
                #
                # READ ONLY, deliberately. The operator's words: "I don't yet want to
                # mess up anyone's emails or websites." `message.send` and
                # `message.forward` are the two operations that put words outside the
                # box, and PIM employs neither — so there is no grant an operator could
                # write, however generous, that would let this app send anything.
                # `alias.list` joined 2026-08-28 — a READ of which addresses exist on
                # this instance's domain, where each forwards, and how far each has got
                # through send-as confirmation. PIM's Email tab is what replaces the
                # legacy dashboard's, and that tab is a list of addresses.
                #
                # THREE administrative writes joined 2026-09-10, on the operator's
                # decision: "the email tab should be properly configured for a user to
                # edit emails or re run the verifications to be sent for authorization".
                # `forwarding.set` (where their own address hands mail on),
                # `identity.verify_request` (re-send the send-as setup email) and
                # `identity.remind` (nudge its owner). Each is a separate grant, and the
                # two that SEND are confirmed by typing the address. `alias.create` and
                # `alias.remove` stay off — they change what exists on a domain FND
                # answers for, and remain the operator's — as do `message.send` and
                # `message.forward`, for the reason above.
                operations=("mailbox.list", "message.fetch", "alias.list",
                            "forwarding.set", "identity.verify_request", "identity.remind"),
            ),
            PortDeclaration(
                port_id="site_hosting",
                why=(
                    "the client's own site: which pages it has, and the writing they "
                    "publish to it. DECLARED, not bound — the operator selects an "
                    "extension on Ports and writes the grant afterwards, so this ships "
                    "able to do nothing"
                ),
                # OPERATIONS, not calls: WHICH extension serves the tree — FND's own
                # host, a hosted CMS, an object store — is the operator's later choice.
                #
                # ADDED 2026-08-26, and this manifest previously recorded the opposite:
                # "no declaration means no path to a live site exists, which is the
                # read-only constraint holding until the operator confirms the cutover."
                # That was true and it was superseded by an explicit request for client
                # authoring. The path now exists and is still shut: declaring is not
                # binding, and binding is not granting.
                # `analytics.read` joined 2026-08-28. It is the only one here that
                # touches nobody's words — it counts what already happened — and the only
                # one an unattended routine performs, so an operator can grant the
                # nightly refresh exactly this and leave the other three withheld.
                # `content.replace` and `asset.upload` joined 2026-08-29. They were
                # withheld on 2026-08-26 under "I don't yet want to mess up anyone's
                # emails or websites"; the operator then asked for exactly them — the
                # design page should "allow for image changes and icons and text edits
                # that change the hosted site".
                #
                # SEPARATE, and that is what makes the new position sayable. Editing
                # words already on a page is not the risk of putting a new file at a
                # public URL, and neither is publishing a piece — so an operator may
                # grant any one of the three and withhold the others.
                operations=("page.list", "article.publish", "article.retire",
                            "analytics.read", "content.replace", "asset.upload"),
            ),
            # WHY THERE IS STILL NO `commerce_offering` HERE, stated because its absence
            # was the one gap in this manifest that nothing recorded a reason for.
            #
            # A commerce port is a path to take PAYMENT on the client's behalf. That is
            # outward-facing in a way `site_hosting` is not: a mistaken publish is
            # embarrassing and reversible, and a mistaken charge is somebody's money.
            # `brevat` already declares vendor calls there, so the seam exists and PIM
            # declaring it is a cutover decision, not a build step.
            #
            # And the two nobody had asked about, recorded 2026-08-26 when the check
            # above stopped naming a written-down pair and started deriving the absent
            # set from the register:
            #
            #   sms_provider — nothing fills it. It is a port type with no eligible
            #                  extension anywhere in the catalogue, so declaring it would
            #                  put a row on this app's Ports table that could never be
            #                  bound. An app employing a seam nothing can stand in is the
            #                  decoration this codebase refuses.
            #   ai_provider  — a different app's. `oveure` declares it because knowledge
            #                  work is what asks a model a question; PIM is a client's
            #                  record of a service relationship, and relaying their words
            #                  to a vendor is not part of that relationship. If it ever
            #                  becomes part of it, it is a decision with a conversation
            #                  behind it, not a line added here.
            #
            #   payment_instrument — the OTHER side of the relationship (2026-09-16).
            #                  It is the seam FND charges a CLIENT through: vault the
            #                  card they put on file at signup, describe it, charge it,
            #                  detach it. Declaring it here would give the client's own
            #                  app the operations that charge its owner. PIM shows the
            #                  RECORD — brand, last four, expiry, state — handed in by
            #                  the host on the `account` fact, and nothing on this
            #                  instance can act on the instrument. The port is the
            #                  grantor package's, on FND's instance, where the binding
            #                  is the operator's act. A client's right to take their
            #                  card back is `instrument.detach`, and it reaches the
            #                  grantor through a door of its own rather than through a
            #                  grant on the client's app.
            #
            # An absence with a recorded reason is a decision; an absence without one is
            # indistinguishable from an oversight, and the next reader cannot tell which
            # they are looking at. See §8 item 6 of the consolidation plan.
        ),
    )


def _grantor_package() -> ToolPackage:
    """GRANTOR — the operator's half of the hosting relationship, on FND and nowhere else.

    The depiction is explicit about where it runs: *"since the grantor application is only
    on the FND instance, the actual application UI provided should allow me to change the
    prices of services"*. And about who does what: *"clients merely interface with the
    private channel to configure account information ... as well as obtain API keys"*.

    ## Why an app rather than more channel

    `micyte.channels.register` REFUSES any channel that declares writes, and the module
    says why: an anonymous request resolves to the operator identity, so "no write path
    exists" is the only safe posture. Setting a price is a write. So the grantor CHANNEL
    (the client's read-only view of their own row) and the grantor APPLICATION (this) are
    two things wearing one name, and separating them is what lets the channel keep its
    refusal untouched while the operator gets a surface that writes.

    ## It claims two tools and PROVISIONS three books

    This package does not declare `offer_ledger` and cannot: it is brevat's, and a tool
    belongs to exactly one lineage. It does not declare `sales_ledger` for the same reason.
    The first cut listed both, and `installable_tools` refused it — *"picking one here
    would decide, invisibly, whose requirements get provisioned into the operator's
    instance."*

    The rule is no obstacle to reusing them, because a package does not decide what OPENS.
    Those tools apply to the `invoice` and `offer` archetypes, so they open on any sandbox
    holding a document of that archetype — including this one. What a package decides is
    what gets PROVISIONED, which is what `app_sandbox.documents` is for: "the app's own
    datum-doc defaults BEYOND what its tools require".

    So the books are provisioned here and rendered by tools that already exist. Nothing is
    duplicated, and no second definition of what a charge IS gets written.

    `credit_ledger` IS claimed, because it is genuinely this lineage's: a farm has no free
    trials, and nothing else offers the tab. So is `subscription_book` (TASK-2026-08-24-010):
    what an alias HOLDS is a hosting fact, and a farm has no aliases.

    So is `grantor_permissions` (2026-08-29). What every connected port MAY do is the
    operator's fact about the hosting relationship — a farm has no clients' bindings to
    permit — and it belongs beside the rate card rather than on Utilities > Ports, because
    `port_binding_write_runtime` keeps connecting and permitting apart on purpose: "a form
    that did both would make describing and permitting one gesture, and the gesture people
    make is the permissive one". Two surfaces, two acts. What changed is that the second
    one stopped requiring a text editor.

    The cost book is provisioned and given no writing surface, and this package does not
    declare `supply_ledger` — deliberately. In a farm sandbox `invoices` is what the farm
    bought; in the grantor sandbox it is what AWS charged FND, written by a PROJECTION from
    the operator tolling ledger (phase D) rather than by an operator typing entries. A
    hand-entry surface for it would invite a cost figure that disagrees with the ledger it
    mirrors.

    ## The namespace is STATED, not inherited

    `namespace="farm"`, against the grain of the two most recent apps, and measured rather
    than assumed. INHERIT resolves from the anchor's `copied_from`, and the grantor
    anchor — minted 2026-08-21 as a farm-template clone — records no such key; only a
    `legacy_alias` naming the agro_erp anchor it came from. So an inherited claim would
    fall back to the instance's core `system` anchor, and FND's speaks SYSTEM, the one
    namespace of six with no lcl vocabulary at all. That is precisely the Oveure defect,
    and this sandbox is guaranteed to hit it because FND is the only instance it runs on.

    `field_registry` already states `"grantor": FARM`, and the claim registered at install
    has to agree with it or `register_instance_namespace` refuses — which is the check that
    makes stating it safe rather than a second opinion.
    """
    return _package(
        "grantor",
        version="0.2.0",
        label="Grantor",
        summary=(
            "The operator's side of the hosting relationship: what each service is "
            "priced at, what each alias has been charged, and what has been credited "
            "back. Prices are set here; the cost they are measured against is projected "
            "from the operator tolling ledger. FND only."
        ),
        tools=("grantor_overview", "credit_ledger", "subscription_book",
               "grantor_tolling", "grantor_permissions"),
        icon="grantor",
        hub_tool="grantor_overview",
        app_sandbox=AppSandbox(
            namespace="farm",
            why=(
                "the grantor sandbox's anchor is a farm-template clone and records no "
                "`copied_from`, so an INHERITED claim would resolve through FND's core "
                "`system` anchor — the one namespace with no lcl vocabulary. Stated, and "
                "checked against `field_registry`'s own `grantor: farm` at install"
            ),
            # The books this app keeps that its own two tools do not require. `credits`
            # arrives with `credit_ledger`; these three do not, because the tools that
            # render them belong to brevat — and a package may not claim another lineage's
            # tool to get at the document it opens on.
            documents=(
                DocumentRequirement(
                    name="offering", archetype="offer",
                    why="what each hosted service is priced at, per unit — the price list "
                        "the operator sets and every charge is drawn from"),
                DocumentRequirement(
                    name="sales", archetype="invoice",
                    why="what each alias was charged: the service, the quantity, the "
                        "amount and when — the event log the depiction asks for"),
                DocumentRequirement(
                    name="invoices", archetype="invoice",
                    why="what AWS charged FND, residue included. Written by a PROJECTION "
                        "from the operator tolling ledger, never by hand, so it is "
                        "provisioned with no writing surface offered"),
            ),
        ),
        port_declarations=(
            PortDeclaration(
                port_id="commerce_offering",
                why=(
                    "charging a client against the payment method they authorised. "
                    "DECLARED and not bound: vaulting a card means FND can take money "
                    "without the client present, which is the operator's decision on "
                    "Ports and nobody else's"
                ),
                calls=(
                    DeclaredCall(service="paypal", operation="order.create"),
                    DeclaredCall(service="paypal", operation="order.capture"),
                ),
            ),
            PortDeclaration(
                port_id="payment_instrument",
                why=(
                    "the card a client put on file at signup: vault it once, describe "
                    "it to the surfaces that draw it, charge it after the trial, detach "
                    "it when the client asks. DECLARED and not bound (2026-09-16): no "
                    "fill exists on this build, so nothing can move money until the "
                    "operator binds one on Ports — and a fill must be one whose card "
                    "fields the processor hosts, because no operation here takes a "
                    "card number"
                ),
                # OPERATIONS, not calls, unlike `commerce_offering` above: that port's
                # grain belongs to PayPal (one-off orders a site takes), while this one
                # names its own four so an operator can grant `instrument.charge` to
                # the billing routine alone and withhold it from every surface.
                operations=("instrument.vault", "instrument.describe",
                            "instrument.charge", "instrument.detach"),
            ),
        ),
    )


def _oveure_package() -> ToolPackage:
    """The knowledge shelf (TASK-2026-08-14-002 Phase 5) — the third lineage.

    Its own builder only because its declarations derive from other modules' constants
    (`OVEURE_PROVIDERS`, the port's operation grain) rather than being restated here —
    the `JOB_LOG` rule, applied to a manifest.
    """
    from micyte.ports.ai_provider import OPERATION_MESSAGES_CREATE
    from micyte.ports.email_provider import (
        OPERATION_MAILBOX_LIST as EMAIL_MAILBOX_LIST,
    )
    from micyte.ports.email_provider import (
        OPERATION_MESSAGE_FETCH as EMAIL_MESSAGE_FETCH,
    )
    from micyte.ports.email_provider import (
        OPERATION_MESSAGE_FORWARD as EMAIL_MESSAGE_FORWARD,
    )
    from micyte.ports.email_provider import (
        OPERATION_MESSAGE_SEND as EMAIL_MESSAGE_SEND,
    )
    from micyte.ports.sms_provider import (
        OPERATION_MESSAGE_SEND as SMS_MESSAGE_SEND,
    )

    from .note_books import OVEURE_PROVIDERS

    return _package(
        "oveure",
        # 1.1.0: the sandbox files its documents on a reserved `documents` branch of its
        # own local domain, so a node DENOTES a document by naming its slot rather than by
        # the document's filename. Universal from 2026-08-20; no longer declared here.
        version="1.2.0",
        label="Oveure",
        summary=(
            "Notes, the domain sheet, and the instance's automation and AI seams. The "
            "AI providers are DECLARED here and bound — and granted — by the operator "
            "on Ports, never by installing."
        ),
        tools=("oveure", "lcl_editor"),
        icon="oveure",
        hub_tool="oveure",
        app_sandbox=AppSandbox(
            # INHERIT ("" — see AppSandbox): the knowledge sandbox's anchor is copied
            # verbatim from the instance's own core anchor, so its numbering is whatever
            # THAT anchor speaks, and the installer resolves it per instance. This
            # shipped as a static "system", which is the namespace of exactly one core
            # anchor (FND's) — one with NO lcl-node vocabulary, so the Domain tab could
            # never have minted there — while the farm anchors speak FARM and the client instance's
            # speaks REGISTRAR. Measured in the gates follow-through, with the seeding
            # decision it gated: the installer now seeds a provisioned local domain with
            # its type root and refuses, by name, a namespace that cannot express one.
            namespace="",
            why=(
                "A knowledge sandbox's anchor is copied verbatim from the instance's "
                "own core anchor (scripts/bootstrap_app_sandbox.py), so its namespace "
                "is INHERITED — resolved at install, never stated as a token that "
                "could disagree with the copy."
            ),
            # Oveure's whole substrate: a node denotes a document by naming its slot, and
            # the slots live on the reserved `documents` branch.
        ),
        # The app's ports, each at the withholdable grain: every provider is its own
        # SERVICE, so a grant over one is never a grant over another, and each single
        # operation is the call that sends the operator's text off-box. All declared,
        # none bound: the ask relay ships denied, and the email/SMS seams (the Oveure
        # refinement — declared-available and unused by the operator's explicit wish)
        # have no peripheral, no route and no client behind them at all.
        port_declarations=(
            PortDeclaration(
                port_id="ai_provider",
                why=(
                    "the ask relay — a draft sent to a hosted model, the reply "
                    "returned unsaved; which providers may be asked is the "
                    "operator's grant, per provider"
                ),
                calls=tuple(
                    DeclaredCall(service=provider, operation=OPERATION_MESSAGES_CREATE)
                    for provider in OVEURE_PROVIDERS
                ),
            ),
            # The two messaging seams declare OPERATIONS, not a vendor. Which service
            # actually carries a message is the extension the instance selected on
            # Ports — FND relaying it, or a direct provider adapter — and that choice is
            # made long after this manifest was written. Naming `aws_ses` here (as this
            # shipped) pinned the app to one answer and would have stopped matching the
            # moment an operator picked another.
            PortDeclaration(
                port_id="email_provider",
                why=(
                    "the mail this instance receives and answers: read what arrived, "
                    "reply from the same address, or hand it to a person. Which "
                    "extension carries it, and which of the four an operator permits, "
                    "are both decided on Ports"
                ),
                operations=(
                    EMAIL_MAILBOX_LIST,
                    EMAIL_MESSAGE_FETCH,
                    EMAIL_MESSAGE_SEND,
                    EMAIL_MESSAGE_FORWARD,
                ),
            ),
            PortDeclaration(
                port_id="sms_provider",
                why=(
                    "the text-message rail, same posture: declared before any use "
                    "exists so the seam is visible on Ports, never granted by shipping"
                ),
                operations=(SMS_MESSAGE_SEND,),
            ),
        ),
        scoped_features=(
            ScopedFeature(
                tool_id="lcl_editor",
                scope="app_sandbox",
                why=(
                    "The hub's Domain tab is this sandbox's own sheet, whole; the "
                    "standalone editor follows the instance switcher across sandboxes."
                ),
            ),
        ),
    )


def _enchir_package() -> ToolPackage:
    """Enchir — the projects a client keeps, and how their website offers them up.

    Operator, 2026-09-01: "a new application called 'Enchir' for people like KKO and BHN
    to manage projects and how they are offered up to their websites". The tool has been
    live since 2026-09-03 as a bare palette entry; this is the manifest that says what it
    EMPLOYS, so the Ports surface can show the seam and an operator can grant it.

    NO app sandbox. Enchir's subject is the documents an instance already keeps, in
    whichever sandbox it is opened over — a sandbox of its own would be a second place for
    a project to live and a second answer to "what do I have". What it employs is the
    site: reading which profiles the site allocates (`page.list`) and rewriting one
    (`profile.edit`). Declared, not bound, and not granted — the same posture as PIM's.
    """
    from micyte.ports.site_hosting import (
        OPERATION_ASSET_UPLOAD,
        OPERATION_PAGE_LIST,
        OPERATION_PROFILE_EDIT,
        OPERATION_PROJECT_EXPORT,
    )

    return _package(
        "enchir",
        version="1.2.0",
        label="Enchir",
        summary=(
            "The projects, commissions and pieces of work an instance keeps, grouped by "
            "what they are — and, when a website is connected, the profiles that site "
            "offers them up through: which photograph stands for each, the order of "
            "the rest, and the short and long description."
        ),
        tools=("enchir",),
        icon="enchir",
        hub_tool="enchir",
        port_declarations=(
            PortDeclaration(
                port_id="site_hosting",
                why=(
                    "the client's own site: which profiles it allocates, the one "
                    "edit that arranges and describes a project on it, and the upload "
                    "that adds a photograph to one. Reading is `page.list` — the same "
                    "disclosure PIM's Design tab makes — the edit is fenced to the "
                    "profile's own gallery, and the upload to the site's own pool"
                ),
                operations=(OPERATION_PAGE_LIST, OPERATION_PROFILE_EDIT,
                            OPERATION_ASSET_UPLOAD, OPERATION_PROJECT_EXPORT),
            ),
        ),
    )


class LocalPackageSource:
    """What this build ships. The ``official`` source is the seam, and is not built."""

    source_id = SOURCE_LOCAL

    def available(self) -> tuple[ToolPackage, ...]:
        return catalogue()


def packages_by_tool() -> dict[str, ToolPackage]:
    """``tool_id -> its package``. Raises if two packages claim one tool."""
    return installable_tools(catalogue())


# The Protocol is runtime_checkable, so this is a real check rather than a comment.
assert isinstance(LocalPackageSource(), ToolPackageSource)

__all__ = ["LocalPackageSource", "catalogue", "packages_by_tool"]
