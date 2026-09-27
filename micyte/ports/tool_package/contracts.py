"""What a tool PACKAGE is, and what installing one may and may not do.

The operator's framing: the marketplace is a **port**, like PayPal. ``micyte.com`` is the
authoritative source of packages; somebody may side-load a custom one, and a side-loaded
package simply is not listed. That is the same shape ``port_binding`` already draws — the
port declares what a thing is, a *source* says where it came from, and the deployment
decides what it may do.

## Installing grants NOTHING, and this is the whole design

``tool_exposure`` is a PRESENTATION control and its documented default is **open**:
``tool_exposure_enabled`` returns True for a tool the config does not name, because
"exposure is not authorization". What a tool may WRITE is decided by
``micyte.ports.datum_write_policy``, which denies on an empty grant set.

So *install* means: this instance shows this tool, and its requirements have been
provisioned. It does not mean the tool may write anything. ``port_binding`` states the
reason plainly and it applies here word for word — *an adapter that arrives able to act
because it was merely installed is the shape of a supply-chain problem.* A marketplace is
exactly where that goes wrong, so the two registers stay apart: a package declares
``writes`` so an operator can SEE what it would ask for, and that declaration is never a
grant.

## A package declares what it NEEDS, not just what it is

The operator's other requirement — tools should "dictate the required source reference
files and the blank datum docs to be created for their use" — is
:class:`ToolRequirement`. Both halves already exist as mechanisms:

* a **source** is a row in the consumer's ``sources`` manifest, pinning a document another
  sandbox publishes (``micyte.core.sources``);
* a **blank document** is what ``create_document_rows`` writes, as
  ``bootstrap_handyman_sandbox`` does for a new instance.

What was missing is the tool SAYING so, so installing can provision them instead of an
operator running two scripts and remembering the order.

Deliberately NOT here: where packages are stored, how one is fetched, what the marketplace
looks like, or how an instance authenticates to ``micyte.com``. Those are host and adapter
concerns, and this file is a contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.ports.external_call_policy import DeclaredCall
from micyte.ports.port_catalog import port_type

#: Where a package came from. The distinction is the operator's: the marketplace lists what
#: the authority publishes, and a side-loaded package runs but is not listed — so an
#: instance can always say which of its tools somebody vouched for.
SOURCE_OFFICIAL = "official"
SOURCE_LOCAL = "local"
SOURCES: tuple[str, ...] = (SOURCE_OFFICIAL, SOURCE_LOCAL)


class ToolPackageError(ValueError):
    """A package that cannot be read, or that claims something it may not."""


@dataclass(frozen=True)
class SourceRequirement:
    """A document in ANOTHER sandbox this package needs to read.

    Provisioned as a row in this sandbox's ``sources`` manifest. ``sandbox`` and ``document``
    name it; ``why`` is required and is not decoration — ``sources_manager`` shows declared
    reads to an operator, and a row nobody can explain is one nobody can decide to retire.
    """

    sandbox: str
    document: str
    why: str

    def __post_init__(self) -> None:
        for name in ("sandbox", "document", "why"):
            if not str(getattr(self, name) or "").strip():
                raise ToolPackageError(f"a source requirement needs a {name}")


@dataclass(frozen=True)
class DocumentRequirement:
    """A BLANK document this package needs the sandbox to hold.

    ``archetype`` is what its rows will be, so provisioning can seed a document whose shape
    is already the one the tool's writes produce — and so an operator can see, before
    installing, what kind of thing is about to be created in their instance.
    """

    name: str
    archetype: str
    why: str
    #: The content hash of the archetype DOCUMENT this package was built against — the
    #: ``<hash>`` segment of its id in the archetype library (operator decision D4,
    #: 2026-09-17). An archetype is a datum document, so it already has a version; this
    #: pins which one. Filled from ``micyte/tools/_archetypes.lock.json`` by the package
    #: builder, never typed by hand, and compared by :func:`unmet_requirements` against
    #: what the instance's library holds — so an instance updating a gadget against a
    #: changed archetype is refused before the change can break it, not after.
    archetype_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("name", "archetype", "why"):
            if not str(getattr(self, name) or "").strip():
                raise ToolPackageError(f"a document requirement needs a {name}")


@dataclass(frozen=True)
class ArchetypeMismatch:
    """An archetype the package was built against and the instance holds differently —
    or not at all (``held == ""``). Both hashes travel so the refusal can say them."""

    name: str
    expected: str
    held: str

    @property
    def sentence(self) -> str:
        if not self.held:
            return f"the library holds no archetype named {self.name!r} (expected {self.expected[:12]}…)"
        return (f"archetype {self.name!r} is {self.held[:12]}… here and this package was "
                f"built against {self.expected[:12]}…")


@dataclass(frozen=True)
class ToolRequirement:
    """Everything a tool needs before it can run: what it reads, and what must exist."""

    sources: tuple[SourceRequirement, ...] = ()
    documents: tuple[DocumentRequirement, ...] = ()
    #: Satisfied by holding ANY ONE of these, not all of them. The general calendar reads
    #: every ``class_log`` document an instance holds, so it is meaningful wherever there is
    #: something to show and nowhere else — which ``documents`` cannot say, because ALL-of
    #: would demand a farm keep a job log. Declaring nothing said it belonged everywhere,
    #: and it landed on the registrar's rail beside the network's own calendar.
    #:
    #: A GATE concept only. ``unmet_requirements`` reports it, and provisioning never acts on
    #: it: "create one of these three" is not a choice an installer may make on an operator's
    #: behalf, and picking the first would decide it invisibly.
    documents_any: tuple[DocumentRequirement, ...] = ()
    #: Logical field names the tool WRITES, resolved through the anchor decoder ring.
    #:
    #: A document requirement asks whether the instance holds the right FILE; this asks
    #: whether its anchor can express the fields the tool puts in it. The two can disagree:
    #: a farm holding ``contacts`` + ``job_log`` passes the document gate, renders the
    #: Contacts tab, and fails every save, because the farm anchor never defined ``email``,
    #: ``website`` or ``ruiqi_id``. Nothing checked that the gate and the write agreed.
    #:
    #: Deliberately not solved by widening ``field_registry.address`` — it refuses on purpose
    #: ("asking where to WRITE a field the anchor has not defined must still fail"), and
    #: giving a farm real contact fields is an additive-field program against its anchor.
    fields: tuple[str, ...] = ()
    #: Archetypes the package pins by hash that the instance holds differently. A
    #: mismatch is not "unmet" — provisioning cannot create the right archetype, and an
    #: install that proceeded would write rows the instance's library does not cover.
    archetypes: tuple[ArchetypeMismatch, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.sources or self.documents or self.documents_any or self.fields
                    or self.archetypes)

    @property
    def is_incompatible(self) -> bool:
        return bool(self.archetypes)


#: The one scope an app tab may currently declare. A tab scoped ``app_sandbox`` renders
#: the app's own sandbox and nothing else; the STANDALONE tool remains the cross-sandbox
#: surface. Held as a tuple so a typo'd scope refuses instead of quietly meaning nothing.
FEATURE_SCOPES: tuple[str, ...] = ("app_sandbox",)


@dataclass(frozen=True)
class ScopedFeature:
    """A shared tool an app's hub embeds as a tab, PINNED to a declared scope.

    The capability-before-surface rule, written as data: the payload builder is the
    primitive, the standalone tool declares "everything, with toggles", and the app tab
    declares this — the same builder pinned to the app's own sandbox. Declaring it on the
    manifest is what lets the two surfaces be checked against each other instead of
    drifting apart.
    """

    tool_id: str
    scope: str
    why: str

    def __post_init__(self) -> None:
        for name in ("tool_id", "scope", "why"):
            if not str(getattr(self, name) or "").strip():
                raise ToolPackageError(f"a scoped feature needs a {name}")
        if self.scope not in FEATURE_SCOPES:
            raise ToolPackageError(
                f"unknown feature scope {self.scope!r}; expected one of {FEATURE_SCOPES}"
            )


@dataclass(frozen=True)
class PortDeclaration:
    """A port this app EMPLOYS, declared on the manifest — never bound by it.

    The same split ``port_binding`` draws, one layer earlier: a *declaration* says the app
    has a seam shaped like this (these writes, these calls); a *binding* is the operator
    filling that seam with an adapter for named sandboxes; and the *grants* are yet
    another decision. Installing an app records the declaration and nothing else — there
    is no grant field here to forget to leave empty.

    ``calls`` versus ``operations``
    -------------------------------
    Both say "this app would call out", and the difference is who decides the SERVICE.

    ``calls`` names a vendor. ``brevat`` means PayPal specifically — capture is PayPal's
    verb, and an operator granting it is granting it over PayPal. ``ai_provider`` is the
    same shape for the same reason: there the service IS the provider, so a grant over
    ``anthropic`` is deliberately not a grant over ``openai``.

    ``operations`` names only the grain, because the service is whichever EXTENSION the
    instance selected for the port. ``oveure`` employs "send a message"; whether that is
    FND relaying it or a direct SES adapter is the operator's choice on Ports, made after
    the app was written. An app hardcoding the service there would pin its manifest to one
    extension and quietly stop matching the moment somebody chose another — which is the
    whole thing the port-type / extension split exists to prevent.
    """

    port_id: str
    why: str
    writes: tuple[DeclaredWrite, ...] = ()
    calls: tuple[DeclaredCall, ...] = ()
    operations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("port_id", "why"):
            if not str(getattr(self, name) or "").strip():
                raise ToolPackageError(f"a port declaration needs a {name}")
        try:
            declared_port = port_type(self.port_id)
        except ValueError as exc:
            raise ToolPackageError(f"port declaration: {exc}") from exc
        object.__setattr__(
            self, "operations",
            tuple(t for t in (str(op or "").strip() for op in (self.operations or ())) if t))
        # An operation the PORT does not name is one no grant can be written about: the
        # grant dimension is the port's vocabulary, so a declaration outside it would show
        # on the Functions table as a row whose permission can never be answered.
        if declared_port.names_its_operations:
            unknown = [op for op in self.operations if op not in declared_port.operations]
            if unknown:
                raise ToolPackageError(
                    f"port declaration {self.port_id!r} names operation(s) the port does "
                    f"not: {', '.join(sorted(unknown))}. It offers "
                    f"{', '.join(declared_port.operations)}."
                )
        elif self.operations:
            raise ToolPackageError(
                f"port {self.port_id!r} names no operations of its own — its grain "
                "belongs to whichever vendor fills it, so declare vendor `calls` instead"
            )
        if not (self.writes or self.calls or self.operations):
            raise ToolPackageError(
                f"port declaration {self.port_id!r} declares no writes, calls or "
                "operations; a seam that would do nothing is not a seam"
            )


@dataclass(frozen=True)
class PortFunction:
    """One callable unit an extension offers on a port — the grain a grant withholds.

    The operator's word for it. A port TYPE says what operations exist; a fill says which
    of them this particular extension actually performs, and ``why`` says what calling it
    costs the instance in disclosure. Both halves are needed on the Functions surface: an
    operator deciding whether to permit ``message.send`` is deciding about words leaving
    the box under their client's name, and a bare operation token does not say that.

    An extension may fill a port PARTIALLY. Offering three of four operations is an honest
    fill; the surface shows the fourth as offered by nobody, which is a truer answer than
    an adapter that accepts the call and raises ``NotImplementedError`` at the provider.
    """

    operation: str
    why: str

    def __post_init__(self) -> None:
        for name in ("operation", "why"):
            if not str(getattr(self, name) or "").strip():
                raise ToolPackageError(f"a port function needs a {name}")
            object.__setattr__(self, name, str(getattr(self, name)).strip())

    def declared_call(self, service: str) -> DeclaredCall:
        """This function as the egress request a grant is judged against.

        Built here so a binding, a routine and the Functions surface all ask the same
        question — the ``port_binding`` rule that the declaration IS the request, never a
        label some second piece of code re-derives.
        """
        return DeclaredCall(service=service, operation=self.operation)


@dataclass(frozen=True)
class PortFill:
    """A port type this package can FILL — what makes a package an EXTENSION.

    The mirror of :class:`PortDeclaration`, and the half that was missing. An app says
    *I employ a seam shaped like this*; an extension says *I can stand in that seam*; and
    the operator's binding is the sentence joining them. Before this, the joining sentence
    was a dotted Python path typed by hand into ``config.json`` — nothing checked it named
    anything installed, nothing checked it fit the port, and no surface could offer a
    choice because there was no list of candidates to offer.

    ``service`` is the external-call token grants name. It belongs to the EXTENSION, not
    to the port: FND relaying a message and a direct SES adapter sending one fill the same
    port and are not the same disclosure, so they must not share a grant.

    ``adapter_id`` is the dotted path the host imports. Stated on the manifest rather than
    in the binding so that selecting an extension is all an operator does — the path is
    the package's own business, and an operator should never be in a position to type one
    wrong.

    Declaring a fill grants NOTHING, exactly as declaring an app port does. It says this
    code exists and fits. Whether it may act is still two decisions away.
    """

    port_id: str
    adapter_id: str
    service: str
    why: str
    functions: tuple[PortFunction, ...] = ()

    def __post_init__(self) -> None:
        for name in ("port_id", "adapter_id", "service", "why"):
            if not str(getattr(self, name) or "").strip():
                raise ToolPackageError(f"a port fill needs a {name}")
            object.__setattr__(self, name, str(getattr(self, name)).strip())
        try:
            filled = port_type(self.port_id)
        except ValueError as exc:
            raise ToolPackageError(f"port fill: {exc}") from exc
        object.__setattr__(self, "functions", tuple(self.functions or ()))
        if not self.functions:
            raise ToolPackageError(
                f"port fill {self.port_id!r} offers no functions, so selecting it would "
                "connect a seam that can do nothing. Say what it performs, or do not "
                "declare the fill."
            )
        seen: set[str] = set()
        for function in self.functions:
            if not isinstance(function, PortFunction):
                raise ToolPackageError("port_fill.functions must hold PortFunction values")
            if function.operation in seen:
                raise ToolPackageError(
                    f"port fill {self.port_id!r} names {function.operation!r} twice"
                )
            seen.add(function.operation)
        # A fill may only offer what the port names — when the port names anything. A port
        # whose grain belongs to its vendor (commerce_offering) is the deliberate
        # exception, and it is asked rather than inferred from an empty tuple.
        if filled.names_its_operations:
            unknown = [f.operation for f in self.functions
                       if f.operation not in filled.operations]
            if unknown:
                raise ToolPackageError(
                    f"port fill {self.port_id!r} offers operation(s) the port does not "
                    f"name: {', '.join(sorted(unknown))}. It offers "
                    f"{', '.join(filled.operations)}."
                )

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(function.operation for function in self.functions)

    def declared_calls(self) -> tuple[DeclaredCall, ...]:
        """Every function as an egress request. One derivation, three consumers."""
        return tuple(function.declared_call(self.service) for function in self.functions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "adapter_id": self.adapter_id,
            "service": self.service,
            "why": self.why,
            "functions": [
                {"operation": f.operation, "why": f.why} for f in self.functions
            ],
        }


@dataclass(frozen=True)
class AppSandbox:
    """The sandbox an app is TIED TO, as the manifest can honestly describe it.

    ``namespace`` is the field-registry namespace the sandbox's anchor speaks — a CLAIM
    about a copied anchor's numbering, carried on the manifest because the anchors cannot
    yet answer for themselves. It is validated where the vocabulary lives
    (``field_registry.register_instance_namespace``), not here: this layer is a contract
    and the decoder ring is ``micyte.core``.

    ``namespace=""`` means **inherit**: the app's sandbox anchor is a verbatim copy of the
    instance's own core anchor, so its numbering is whatever THAT anchor speaks, and the
    installer resolves it per instance (FARM on a farm, REGISTRAR on a trade). A static
    token cannot state that rule — oveure shipped claiming ``"system"``, which is the
    namespace of exactly one instance's core anchor (FND's) and one in which an lcl node
    cannot even be expressed.

    ``documents`` are the app's own datum-doc defaults BEYOND what its tools require —
    the tools' requirements are derived from the tools and never restated.

    There is no ``local_domain_log`` flag. It existed for one day (2026-08-19) while the
    log was scoped to two apps; from 2026-08-20 every sandbox's local domain carries the
    reserved documents branch, because the operator made the log "a canonical default
    document for each sandbox, similar to that of the anchor file". A flag for something
    universal is a flag whose false branch nothing tests.
    """

    namespace: str
    why: str
    documents: tuple[DocumentRequirement, ...] = ()

    @property
    def inherits_namespace(self) -> bool:
        """True when the claim is "whatever the instance's own core anchor speaks"."""
        return not str(self.namespace or "").strip()

    def __post_init__(self) -> None:
        if not str(self.why or "").strip():
            raise ToolPackageError("an app sandbox needs a why")


@dataclass(frozen=True)
class ToolPackage:
    """One installable unit: some tools, what they need, and what they would write.

    A package whose ``hub_tool`` is set is an **app**: a package that is foremost a
    tabular (the hub is a tabbed composite), tied to its own sandbox (``app_sandbox``),
    shipping defaults for datum docs, and employing ports for some operations
    (``port_declarations``). An app is NOT a fourth register — its tabs are registered
    tools, its writes are ``DeclaredWrite``s, its calls live behind port bindings — and
    installing one still grants nothing.
    """

    package_id: str
    version: str
    label: str
    summary: str
    source: str = SOURCE_LOCAL
    #: The ``tool_id``s this package installs. A package with none installs nothing.
    tools: tuple[str, ...] = ()
    requires: ToolRequirement = field(default_factory=ToolRequirement)
    #: What the package's tools DECLARE they write. Shown to the operator before installing
    #: so the answer to "what will this be able to do" is on the screen where they decide.
    #: **Never a grant** — see the module docstring.
    writes: tuple[DeclaredWrite, ...] = ()
    icon: str = ""
    #: The APP half, all optional. A package with a ``hub_tool`` is an app; the other
    #: three describe what that app declares. See the class docstring.
    hub_tool: str = ""
    app_sandbox: AppSandbox | None = None
    port_declarations: tuple[PortDeclaration, ...] = ()
    scoped_features: tuple[ScopedFeature, ...] = ()
    #: The EXTENSION half. A package with ``port_fills`` can stand in a port an app
    #: employs; the instance selects it on Utilities > Ports. Orthogonal to the app half
    #: on purpose — a package may be an app, an extension, both, or neither — because
    #: "what this shows you" and "what this connects for you" are different questions and
    #: a package answering only the second installs no tools at all.
    port_fills: tuple[PortFill, ...] = ()

    def __post_init__(self) -> None:
        for name in ("package_id", "version", "label"):
            if not str(getattr(self, name) or "").strip():
                raise ToolPackageError(f"a package needs a {name}")
        if self.source not in SOURCES:
            raise ToolPackageError(
                f"unknown package source {self.source!r}; expected one of {SOURCES}"
            )
        hub = str(self.hub_tool or "").strip()
        if hub and hub not in self.tools:
            raise ToolPackageError(
                f"hub tool {hub!r} is not among the package's tools; an app's hub is one "
                "of the things it installs, not a reference to somebody else's"
            )
        if not hub and (self.app_sandbox or self.port_declarations or self.scoped_features):
            raise ToolPackageError(
                f"package {self.package_id!r} declares app parts without a hub_tool; "
                "an app is a package with a hub, and app declarations on a plain package "
                "would install behavior nothing on screen accounts for"
            )
        # `port_fills` is deliberately NOT in that check: an extension is exactly a
        # package with no hub and no tools, and requiring one would force every adapter to
        # ship a screen nobody asked for.
        fills = tuple(self.port_fills or ())
        object.__setattr__(self, "port_fills", fills)
        for fill in fills:
            if not isinstance(fill, PortFill):
                raise ToolPackageError("package.port_fills must hold PortFill values")
        filled_ports = [fill.port_id for fill in fills]
        if len(set(filled_ports)) != len(filled_ports):
            raise ToolPackageError(
                f"package {self.package_id!r} fills one port twice — two adapters for one "
                "seam with no rule saying which the instance gets"
            )

    @property
    def is_app(self) -> bool:
        """A package that is foremost a tabular, tied to its own sandbox."""
        return bool(str(self.hub_tool or "").strip())

    @property
    def is_extension(self) -> bool:
        """A package that can FILL a port an app employs.

        Not the opposite of :attr:`is_app` — nothing stops a package from being both, and
        the marketplace shelf renders the two facts separately because an operator asking
        "what will this show me" and one asking "what will this connect" are asking
        different questions about the same row.
        """
        return bool(self.port_fills)

    def fill_for(self, port_id: object) -> PortFill | None:
        """This package's fill for ``port_id``, or ``None``. One fill per port by
        construction, so this cannot be ambiguous."""
        token = str(port_id or "").strip()
        return next((fill for fill in self.port_fills if fill.port_id == token), None)

    @property
    def is_listed(self) -> bool:
        """Does the marketplace list it?

        Only what the authority publishes. A side-loaded package installs and runs — an
        instance is allowed to hold a tool nobody else has — but the marketplace does not
        claim it, because the marketplace's whole content is "what micyte.com vouches for".
        """
        return self.source == SOURCE_OFFICIAL


@runtime_checkable
class ToolPackageSource(Protocol):
    """Where packages come from. The seam the network fetch will fill.

    One method, deliberately: ``available()``. Installing is not on this Protocol because
    installing is not something a SOURCE does — it is something the instance does with a
    package it has, and putting it here would let a remote source install itself.
    """

    source_id: str

    def available(self) -> tuple[ToolPackage, ...]:
        """Every package this source offers."""
        ...


def eligible_fills(port_id: Any, packages: Any) -> tuple[tuple[ToolPackage, PortFill], ...]:
    """The extensions that may fill ``port_id`` — the operator's "if eligible".

    Eligibility is one question with one answer, asked here so the SELECTION form and the
    binding READER cannot disagree about it. A form that offered a candidate the reader
    then dropped would look, from the operator's side, exactly like binding not working;
    the inverse — a reader accepting what the form would never have offered — is how a
    hand-edited config quietly acquires an adapter that does not fit the seam.

    Raises :class:`ToolPackageError` on an unknown port rather than answering "nothing is
    eligible", because those are different facts and only one of them is the operator's to
    fix by installing something.
    """
    token = str(port_id or "").strip()
    try:
        port_type(token)
    except ValueError as exc:
        raise ToolPackageError(f"eligible_fills: {exc}") from exc
    out: list[tuple[ToolPackage, PortFill]] = []
    for package in packages or ():
        fill = package.fill_for(token)
        if fill is not None:
            out.append((package, fill))
    return tuple(out)


def extensions(packages: Any) -> tuple[ToolPackage, ...]:
    """Every package among ``packages`` that can fill some port."""
    return tuple(package for package in (packages or ()) if package.is_extension)


def installable_tools(packages: Any) -> dict[str, ToolPackage]:
    """``tool_id -> the package that installs it``.

    Two packages claiming one tool is a REGISTRATION ERROR rather than something to resolve
    by picking one: the choice would silently decide which package's requirements get
    provisioned, which is the same reasoning ``_write_owners`` applies to a declared action.
    """
    out: dict[str, ToolPackage] = {}
    for package in packages:
        for tool_id in package.tools:
            existing = out.get(tool_id)
            if existing is not None and existing.package_id != package.package_id:
                raise ToolPackageError(
                    f"{tool_id!r} is claimed by both {existing.package_id!r} and "
                    f"{package.package_id!r}. Picking one here would decide, invisibly, "
                    "whose requirements get provisioned into the operator's instance."
                )
            out[tool_id] = package
    return out


def unmet_requirements(
    package: ToolPackage, *, held_documents: Any, declared_sources: Any,
    resolvable_fields: Any = None, held_archetypes: Any = None,
) -> ToolRequirement:
    """What ``package`` still needs, given what the sandbox already holds and declares.

    Pure: the caller passes what it read. Returning the same shape it was given means the
    install path and the "what would this do" preview are the same function, so the preview
    cannot promise something the install then does differently.

    ``resolvable_fields`` is the set of logical field names the sandbox's ANCHOR defines —
    the caller resolves it, because this layer is a contract and the decoder ring is
    ``micyte.core``. ``None`` means "not known", and then the field check is SKIPPED rather
    than failed: an unreadable namespace must not hide a tool, for the same reason
    ``held_documents is None`` leaves the rail alone.

    ``held_archetypes`` is ``{archetype name: document hash}`` read off the instance's
    archetype library; ``None`` skips the pin check the same way. A requirement that pins
    no hash is not checked — a package built before the lockfile existed says nothing
    about which archetype it meant, and silence is not a mismatch.
    """
    held = {str(name) for name in held_documents}
    declared = {(str(sandbox), str(document)) for sandbox, document in declared_sources}
    requires = package.requires
    mismatches: list[ArchetypeMismatch] = []
    if held_archetypes is not None:
        library = {str(k): str(v) for k, v in dict(held_archetypes).items()}
        seen: set[str] = set()
        for requirement in (*requires.documents, *requires.documents_any):
            expected = str(requirement.archetype_hash or "")
            if not expected or requirement.archetype in seen:
                continue
            seen.add(requirement.archetype)
            actual = library.get(requirement.archetype, "")
            if actual != expected:
                mismatches.append(ArchetypeMismatch(
                    name=requirement.archetype, expected=expected, held=actual))
    return ToolRequirement(
        sources=tuple(
            source for source in requires.sources
            if (source.sandbox, source.document) not in declared
        ),
        documents=tuple(
            document for document in requires.documents
            if document.name not in held
        ),
        # ANY-of: unmet only when the sandbox holds NONE of them. Reported whole, so the
        # operator sees the alternatives rather than one arbitrarily-chosen name.
        documents_any=(
            ()
            if not requires.documents_any
            or any(d.name in held for d in requires.documents_any)
            else requires.documents_any
        ),
        fields=(
            ()
            if resolvable_fields is None
            else tuple(f for f in requires.fields if f not in set(resolvable_fields))
        ),
        archetypes=tuple(mismatches),
    )


FITS = "fits"
UNMET = "unmet"
INCOMPATIBLE = "incompatible"


def compatibility(unmet: ToolRequirement) -> str:
    """One word for an install or update decision, from what :func:`unmet_requirements`
    reported: ``incompatible`` (an archetype pin disagrees — refuse; provisioning cannot
    fix it), ``unmet`` (something to create or declare first), ``fits``."""
    if unmet.is_incompatible:
        return INCOMPATIBLE
    if not unmet.is_empty:
        return UNMET
    return FITS


__all__ = [
    "FEATURE_SCOPES",
    "FITS",
    "INCOMPATIBLE",
    "SOURCES",
    "SOURCE_LOCAL",
    "SOURCE_OFFICIAL",
    "UNMET",
    "AppSandbox",
    "ArchetypeMismatch",
    "DocumentRequirement",
    "PortDeclaration",
    "PortFill",
    "PortFunction",
    "ScopedFeature",
    "SourceRequirement",
    "ToolPackage",
    "ToolPackageError",
    "ToolPackageSource",
    "ToolRequirement",
    "compatibility",
    "eligible_fills",
    "extensions",
    "installable_tools",
    "unmet_requirements",
]
