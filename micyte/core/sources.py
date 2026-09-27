"""Sources manifests, made readable: what one sandbox is declared to read from another.

A sandbox is isolated. When it needs something another sandbox holds, that other
sandbox **publishes** the document and the consumer **declares** it — a row in the
consumer's ``sources`` document naming the document and pinning its content hash.
That declaration has existed as data since the mycelium-network work; until now
nothing read it back, so every cross-sandbox read in the codebase reached past the
manifest to a hardcoded sandbox constant. This module is the read side.

The rule it enforces is narrow and worth stating plainly: **a consumer resolves a
document by the name it declared, or it does not get the document.** Undeclared
reads are not refused with an error — they simply have no accessor here, which is
the same posture the open channel routes take toward writes. Absence beats refusal.

Two costs, kept separate
------------------------
*Declaration* is a name lookup and is cheap enough for a hot path. *Verification*
recomputes a content hash and is not. So ``verify=False`` (the default) answers
"is this declared, and is it here?" while ``verify=True`` additionally answers "is
it what was pinned?" — the same split ``check_denotation(deep=False)`` already
makes, and for the same reason.

Two hash families
-----------------
The ``rf.3-1-12`` cell carries a sha256, but not always of the same thing:

* ``datum_document`` rows (the channel manifests) pin the **document-id version
  hash** — already present in the canonical id, so verifying costs nothing.
* ``boundary`` / ``taxonomy`` / ``profiles`` / ``events`` rows (the network and
  farm manifests) pin the **MSS bitstream hash** of the document's datum closure,
  which must be encoded to check and needs the catalog index.

These are different numbers for the same document: ``registrar.fnd_ag_profiles``
is ``73b2207a…`` in the first family and ``734427ec…`` in the second. A resolver
that assumed one family would report every row of the other as total drift, so the
family is dispatched from the row's declared kind, and a kind this module does not
recognize yields ``unverifiable`` — never a false ``stale``.

Fault asymmetry
---------------
After the denotation-coherence rule: gate on what has a mechanical fix, report what
needs a decision about the data. A **stale** pin is a fault — the fix is to re-pin
it. A **missing** source (both farm manifests still declare a ``calendar`` document
that registrar retired) or an **unverifiable** one is open: someone must decide
whether to retire the row or republish the document, and a gate that fails forever
on it only teaches everyone to ignore the gate.

Pure: no I/O, no MOS, no filesystem. Callers pass the documents they already read.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from micyte.core.datum_ops import field_registry as _fr
from micyte.core.document_naming import parse_canonical_document_id

#: The reserved name of a sandbox's manifest document.
MANIFEST_DOCUMENT = "sources"

#: The manifest's own identity row. It carries no pinned hash, which is how it is
#: told apart from a resource row — NOT by the absence of an msn cell, which the
#: channel-shaped manifests legitimately lack.
IDENTITY_ADDRESS = "4-9-1"

# The registrar namespace is borrowed by every manifest regardless of the sandbox
# that holds it, so these are resolved explicitly rather than by sandbox lookup:
# NAMESPACE_BY_SANDBOX has no entry for a channel sandbox at all.
_NODE = _fr.marker(_fr.REGISTRAR, "msn_id")             # rf.3-1-2
_NAME = _fr.marker(_fr.REGISTRAR, "title")              # rf.3-1-3
_HASH = _fr.marker(_fr.REGISTRAR, "mss_source_binary")  # rf.3-1-12
_KIND = _fr.marker(_fr.REGISTRAR, "resource_kind")      # rf.3-1-14

#: Which hash a row's kind pins. ``document`` = the document-id version hash;
#: ``bitstream`` = the MSS hash of the document's datum closure.
KIND_HASH_FAMILY: dict[str, str] = {
    "datum_document": "document",
    "boundary": "bitstream",
    "taxonomy": "bitstream",
    "profiles": "bitstream",
    "events": "bitstream",
}

#: Where a declared source COMES FROM, which is the question the operator asked the source
#: view to answer (2026-08-20). Three answers, and every pin has exactly one:
#:
#: ``own``       this sandbox published it from its own datum documents;
#: ``internal``  another sandbox of THIS instance publishes it;
#: ``external``  it comes from outside this instance — the collective, or a contract payload.
#:
#: Derived, not stored. A pin already names the sandbox it points at, and an instance
#: already knows which sandboxes are its own (``micyte.tools._sandboxes``), so the third
#: bucket needs no new data — only the question being asked.
ORIGIN_OWN = "own"
ORIGIN_INTERNAL = "internal"
ORIGIN_EXTERNAL = "external"


def origin_of(row: Any, *, sandbox: str, instance_sandboxes: Any = ()) -> str:
    """Which of the three ``row`` is, for a consumer in ``sandbox``.

    ``instance_sandboxes`` empty means the caller does not know what this instance holds,
    and everything that is not the sandbox's own reads as ``internal`` — the answer before
    2026-08-20, and the one that is wrong only in the direction of understating how far a
    pin reaches. Claiming ``external`` without knowing would be the other direction, and
    that one tells an operator their data left the building when it did not.
    """
    target = str(getattr(row, "sandbox", "") or "").strip()
    here = str(sandbox or "").strip()
    if target and target == here:
        return ORIGIN_OWN
    known = {str(name or "").strip() for name in (instance_sandboxes or ())}
    if known and target and target not in known:
        return ORIGIN_EXTERNAL
    return ORIGIN_INTERNAL


#: The manifest cell that says a pin ARRIVED rather than being reached for: a source
#: delivered as the payload of a contract. Read off the row's declared kind, because that
#: is where the channel manifests already record it — a pin that cannot say returns ``""``
#: rather than guessing, and the surface then makes no claim either way.
DELIVERED_KINDS: frozenset[str] = frozenset({"contract_payload"})


def is_delivered(row: Any) -> bool:
    """Whether this pin arrived as a contract payload."""
    return str(getattr(row, "kind", "") or "").strip() in DELIVERED_KINDS


FRESH = "fresh"
STALE = "stale"
MISSING = "missing"
UNVERIFIABLE = "unverifiable"

#: Mechanical fix (re-pin the row) — a gate may fail on these.
SOURCE_FAULTS: tuple[str, ...] = (STALE,)
#: The fix is a decision about the data — report, never gate.
SOURCE_OPEN: tuple[str, ...] = (MISSING, UNVERIFIABLE)


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _head(row: Any) -> list[Any]:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return []


def _pairs(head: list[Any]) -> dict[str, str]:
    """Marker -> first value. A manifest row never repeats a marker."""
    out: dict[str, str] = {}
    i = 1
    while i < len(head) - 1:
        out.setdefault(_as_text(head[i]), _as_text(head[i + 1]))
        i += 2
    return out


def bare_hash(value: str) -> str:
    """Strip one ``sha256:`` family marker. Public because a WRITER deciding whether a
    pin needs rewriting has to normalize exactly the way this module compares — a second
    copy of this rule could drift, and the drift would look like a re-pin that silently
    did nothing."""
    text = _as_text(value).strip().lower()
    return text[len("sha256:"):] if text.startswith("sha256:") else text


#: Kept so existing callers (and the archived evidence scripts) keep resolving.
_bare_hash = bare_hash


def _parsed(document: Any) -> Any | None:
    try:
        return parse_canonical_document_id(_as_text(getattr(document, "document_id", "")))
    except Exception:
        return None


@dataclass(frozen=True)
class SourceRow:
    """One declared source, as the manifest states it."""

    address: str
    #: The declared name, exactly as written: ``registrar_registry``, ``taxonomy_txa``.
    declared_name: str
    #: The owning sandbox, recovered from the declared name's prefix.
    sandbox: str
    #: The document name within that sandbox.
    document_name: str
    recorded_hash: str
    kind: str
    #: ``rf.3-1-2`` when present. Farm/network manifests carry it; channel ones do not.
    node: str = ""

    @property
    def hash_family(self) -> str:
        return KIND_HASH_FAMILY.get(self.kind, "")


@dataclass(frozen=True)
class ResolvedSource:
    """A declared source, plus what became of resolving it."""

    row: SourceRow
    document: Any | None
    status: str
    detail: str = ""

    @property
    def is_fault(self) -> bool:
        return self.status in SOURCE_FAULTS

    @property
    def is_readable(self) -> bool:
        """Present and declared. A stale pin is still readable — it is just not
        provably the document that was declared, and the surface must say so."""
        return self.document is not None


@dataclass(frozen=True)
class SourceResolution:
    """Everything a consumer may read, and how far it can be trusted."""

    sandbox: str
    #: False when the sandbox holds no ``sources`` document at all. Distinct from a
    #: manifest that declares nothing: "never declared" and "declared and lost it"
    #: are different facts and a consumer must be able to tell them apart.
    manifest_present: bool
    sources: tuple[ResolvedSource, ...] = ()
    #: Documents that exist in a referenced source sandbox but no row declares.
    #: Reported in both directions after the structure-viewer lesson: a panel that
    #: only iterates manifest rows can never show what the manifest is missing.
    undeclared: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def document(self, declared_name: str) -> Any | None:
        """The document a consumer declared under this name, or None.

        The ONLY read accessor. A name that no row declares resolves to None even
        when the document is sitting right there in the corpus — which is the whole
        point of a declaration.
        """
        for resolved in self.sources:
            if resolved.row.declared_name == declared_name:
                return resolved.document
        return None

    def status_of(self, declared_name: str) -> str:
        for resolved in self.sources:
            if resolved.row.declared_name == declared_name:
                return resolved.status
        return MISSING

    @property
    def faults(self) -> tuple[ResolvedSource, ...]:
        return tuple(r for r in self.sources if r.is_fault)

    @property
    def open_conditions(self) -> tuple[ResolvedSource, ...]:
        return tuple(r for r in self.sources if r.status in SOURCE_OPEN)

    @property
    def is_faithful(self) -> bool:
        """Every declared source is present and pinned to what it holds now."""
        return bool(self.sources) and all(r.status == FRESH for r in self.sources)

    def coverage(self) -> dict[str, Any]:
        """The block a consumer's payload states, so a stale pin is never silent."""
        counts: dict[str, int] = {}
        for resolved in self.sources:
            counts[resolved.status] = counts.get(resolved.status, 0) + 1
        return {
            "sandbox": self.sandbox,
            "manifest_present": self.manifest_present,
            "declared": len(self.sources),
            "statuses": counts,
            "faithful": self.is_faithful,
            "undeclared_available": len(self.undeclared),
            "notes": list(self.notes),
        }


def _split_declared_name(declared: str, sandboxes: set[str]) -> tuple[str, str]:
    """``registrar_fnd_ag_profiles`` -> ``("registrar", "fnd_ag_profiles")``.

    The owning sandbox is encoded in the name's prefix rather than carried in its
    own cell (a shape worth replacing, but it is what is written on disk). Longest
    matching prefix wins, so a sandbox whose name is a prefix of another cannot
    steal the split.

    Not every name is qualified: the farm manifests declare boundary documents by
    bare gazetteer node (``3-2-3-17-14``), because those rows were copied verbatim
    out of a manifest that lived in the sandbox owning them. An unqualified name
    gets an empty sandbox here and is located by :func:`_locate` instead.
    """
    best = ""
    for sandbox in sandboxes:
        if declared.startswith(f"{sandbox}_") and len(sandbox) > len(best):
            best = sandbox
    if best:
        return best, declared[len(best) + 1:]
    return "", declared


def _locate(
    row: SourceRow, by_key: dict[tuple[str, str], Any], consumer: str
) -> tuple[Any | None, str, str]:
    """Find a declared row's document. Returns (document, sandbox, detail).

    A qualified name resolves in its own sandbox or nowhere — the qualification is
    the declaration and guessing past it would defeat the point. An UNQUALIFIED
    name is located: the consumer's own sandbox first, then a unique match across
    the corpus. Uniqueness is the honest rule — a bare name that two sandboxes both
    answer to is ambiguous, and resolving it by picking one would silently bind the
    consumer to whichever sandbox happened to sort first.
    """
    if row.sandbox:
        return by_key.get((row.sandbox, row.document_name)), row.sandbox, ""
    own = by_key.get((consumer, row.document_name))
    if own is not None:
        return own, consumer, ""
    matches = [(sb, doc) for (sb, name), doc in by_key.items() if name == row.document_name]
    if len(matches) == 1:
        sandbox, document = matches[0]
        return document, sandbox, (f"{row.declared_name}: unqualified name located in "
                                   f"{sandbox!r} (it is the only sandbox holding it)")
    if len(matches) > 1:
        owners = ", ".join(sorted(sb for sb, _ in matches))
        return None, "", (f"{row.declared_name}: unqualified name is ambiguous — held by "
                          f"{owners}; qualify the row")
    return None, "", ""


#: The local domain, by its canonical name — the document whose `sources` branch carries
#: a sandbox's own pins. Spelled here rather than imported from `instance_baseline`, which
#: imports this module's neighbours; the name is owned by `document_naming`.
LOCAL_DOMAIN_NAME = "lcl_domain"


def _local_domain_pins(document: Any, *, sandboxes: set[str]) -> tuple[SourceRow, ...]:
    """The pins a local domain's `sources` branch carries, as :class:`SourceRow`.

    A pin's title is ``<msn>.<sandbox>_<name>``: the msn says WHOSE document, and the rest
    is the declared-name spelling :func:`_split_declared_name` already reads. The hash is
    the pin's fourth cell (`Entry.hash`), of the `datum_document` family — a pin names a
    document's version, never a bitstream. ``address`` is the pin's own row, which is what
    tells a re-pin it must rewrite the LOG and not a manifest.
    """
    if document is None:
        return ()
    from micyte.core.datum_ops.local_domain import read_log

    log = read_log(document)
    out: list[SourceRow] = []
    for _slot, entry in log.sources().items():
        title = _as_text(entry.label)
        node, _dot, declared = title.partition(".")
        if not declared:
            node, declared = "", title
        sandbox, document_name = _split_declared_name(declared, sandboxes)
        out.append(SourceRow(
            address=_as_text(entry.address), declared_name=declared, sandbox=sandbox,
            document_name=document_name, recorded_hash=_as_text(entry.hash),
            kind="datum_document", node=node))
    return tuple(out)


#: The public name: the sources WRITER reads a log's pins through it to re-pin them.
local_domain_pins = _local_domain_pins


def manifest_rows(manifest: Any, *, sandboxes: set[str] | None = None) -> tuple[SourceRow, ...]:
    """Parse a ``sources`` document into rows, skipping its identity row."""
    known = sandboxes or set()
    out: list[SourceRow] = []
    for row in getattr(manifest, "rows", ()) or ():
        address = _as_text(getattr(row, "datum_address", ""))
        head = _head(row)
        pairs = _pairs(head)
        recorded = pairs.get(_HASH, "")
        name = pairs.get(_NAME, "")
        # The identity row names the manifest itself; it lives in the reserved 4-9-1
        # slot. Skipping on the ADDRESS rather than on an absent msn cell (as the map
        # viewer's parser did) is what lets this read a channel manifest at all, and
        # skipping on the address rather than on an absent pin is what keeps an
        # UNPINNED resource row — which older manifests carry — from vanishing
        # silently instead of being reported as unverifiable.
        if not name or address == IDENTITY_ADDRESS:
            continue
        sandbox, document_name = _split_declared_name(name, known)
        out.append(SourceRow(
            address=address,
            declared_name=name,
            sandbox=sandbox,
            document_name=document_name,
            recorded_hash=recorded,
            kind=pairs.get(_KIND, ""),
            node=pairs.get(_NODE, ""),
        ))
    return tuple(out)


def resolve_sources(
    documents: Iterable[Any],
    *,
    sandbox: str,
    msn: str = "",
    manifest_name: str = MANIFEST_DOCUMENT,
    verify: bool = False,
    mss_index: dict[str, Any] | None = None,
) -> SourceResolution:
    """Resolve ``sandbox``'s declared sources against the documents in hand.

    ``verify=False`` answers declared-and-present. ``verify=True`` also compares the
    pinned hash against the document as it stands now; bitstream-family rows further
    need ``mss_index`` (from ``build_catalog_index``) and are reported ``unverifiable``
    without it rather than assumed fresh.

    ``manifest_name`` exists because the registrar's own manifest predates the
    reserved name and is called ``network_sources``. New manifests use ``sources``.

    ``msn`` says WHOSE ``sandbox`` is being asked about, and scopes the MANIFEST
    LOOKUP only.

    A sandbox NAME stopped identifying a sandbox when every instance gained its own
    sandbox called ``system``. Keyed on ``(sandbox, name)`` alone, four instances'
    ``system/sources`` documents collapse onto one entry and whichever one wins the
    dict becomes every instance's manifest. Measured on the live portal 2026-08-17:
    all four instances' Compendium showed the SAME 473 imported pins — including
    the client instance and FND, whose ``system`` sandboxes hold no ``sources`` document at all.
    An operator was reading the farm instance's declarations as their own.

    Scoping the RESOLUTION corpus would be the wrong fix and a worse one: both farms'
    manifests deliberately pin documents in FND's ``registrar`` and
    ``taxonomy`` sandboxes, and an msn-filtered corpus would turn 473 legitimate
    cross-instance pins into 473 MISSING rows. Only the question "whose manifest is
    this" is per-instance; "where does this row point" is a question about the whole
    corpus, which is what a source pin is for.

    Blank ``msn`` keeps the old name-only lookup, which is still right for a caller
    holding one instance's documents (every script here) and for a sandbox no two
    instances share.
    """
    corpus: list[tuple[Any, str, str]] = []
    sandboxes: set[str] = set()
    by_address: dict[tuple[str, str, str], Any] = {}
    for document in documents:
        parsed = _parsed(document)
        if parsed is None:
            continue
        sandbox_name = _as_text(parsed.sandbox)
        name = _as_text(parsed.name)
        corpus.append((document, sandbox_name, name))
        sandboxes.add(sandbox_name)
        by_address[(_as_text(getattr(parsed, "msn_id", "")), sandbox_name, name)] = document

    by_key = {(sb, name): doc for doc, sb, name in corpus}
    manifest = (
        by_address.get((_as_text(msn), sandbox, manifest_name))
        if _as_text(msn)
        else by_key.get((sandbox, manifest_name))
    )
    # THE LOCAL DOMAIN'S OWN PINS (2026-09-08). Every sandbox's log carries a `sources`
    # branch (`1-1-3`), each child a pin: `<msn>.<sandbox>_<name>` as its title and the
    # pinned document's content hash as its fourth cell. They are declarations exactly as
    # a manifest row is — "this sandbox reads that document, at that version" — and they
    # resolve through the same corpus and the same hash discipline. A sandbox may hold
    # both a manifest and log pins; both are read, and neither is invented.
    log_rows = _local_domain_pins(
        by_address.get((_as_text(msn), sandbox, LOCAL_DOMAIN_NAME))
        if _as_text(msn) else by_key.get((sandbox, LOCAL_DOMAIN_NAME)),
        sandboxes=sandboxes)
    if manifest is None and not log_rows:
        return SourceResolution(
            sandbox=sandbox,
            manifest_present=False,
            notes=(f"{sandbox} declares no sources (it holds no {manifest_name} document "
                   "and its local domain pins nothing)",),
        )

    rows = ((manifest_rows(manifest, sandboxes=sandboxes) if manifest is not None else ())
            + log_rows)
    resolved: list[ResolvedSource] = []
    notes: list[str] = []
    referenced: set[str] = set()

    for row in rows:
        document, owner, detail = _locate(row, by_key, sandbox)
        if owner:
            referenced.add(owner)
            row = SourceRow(**{**row.__dict__, "sandbox": owner})
        if document is None:
            detail = detail or (f"declared {row.declared_name!r} resolves to no document "
                                f"in {row.sandbox or 'any sandbox'}")
            resolved.append(ResolvedSource(row=row, document=None, status=MISSING, detail=detail))
            notes.append(detail)
            continue
        if detail:
            notes.append(detail)
        if not verify:
            resolved.append(ResolvedSource(row=row, document=document, status=FRESH,
                                           detail="declared and present (hash not checked)"))
            continue
        status, detail = _verify(row, document, mss_index=mss_index)
        resolved.append(ResolvedSource(row=row, document=document, status=status, detail=detail))
        # Every stated detail is surfaced, including a FRESH one: the mis-declared
        # kind is the case that would otherwise pass silently.
        if detail:
            notes.append(detail)

    undeclared = sorted(
        f"{sb}_{name}"
        for (sb, name) in by_key
        if sb in referenced
        and name != MANIFEST_DOCUMENT
        and not any(r.row.sandbox == sb and r.row.document_name == name for r in resolved)
    )

    return SourceResolution(
        sandbox=sandbox,
        manifest_present=True,
        sources=tuple(resolved),
        undeclared=tuple(undeclared),
        notes=tuple(notes),
    )


def _document_hash(document: Any) -> str:
    return _bare_hash(_as_text(getattr(_parsed(document), "version_hash", "")))


def _bitstream_hash(document: Any, mss_index: dict[str, Any] | None) -> str:
    if mss_index is None:
        return ""
    from micyte.core.mss.document_adapter import document_closure_to_mss
    from micyte.core.mss.document_codec import mss_document_hash

    return _bare_hash(mss_document_hash(document_closure_to_mss(document, index=mss_index)))


def _verify(row: SourceRow, document: Any, *, mss_index: dict[str, Any] | None) -> tuple[str, str]:
    """Check a row's pin, and tell a mis-declared kind apart from real drift.

    The declared kind chooses the family. But a pin that fails its own family and
    then matches the OTHER one is not stale — the document is exactly what was
    pinned, and it is the row's kind that is wrong. Reporting that as staleness
    would send an operator to re-pin a row that is already correct, and the re-pin
    would quietly hide the mis-declaration for good.
    """
    family = row.hash_family
    recorded = _bare_hash(row.recorded_hash)
    if not recorded:
        return UNVERIFIABLE, (f"{row.declared_name}: the row declares the document but pins "
                              "no hash, so there is nothing to check it against")
    if not family:
        return UNVERIFIABLE, (f"{row.declared_name}: kind {row.kind!r} pins no known hash "
                              "family, so the pin cannot be checked")
    try:
        current = (_document_hash(document) if family == "document"
                   else _bitstream_hash(document, mss_index))
    except Exception as exc:  # a document whose closure will not encode
        return UNVERIFIABLE, f"{row.declared_name}: hash could not be computed ({exc})"
    if not current:
        if family == "bitstream":
            return UNVERIFIABLE, (f"{row.declared_name}: bitstream pins need the catalog index "
                                  "to check; resolved without verification")
        return UNVERIFIABLE, f"{row.declared_name}: document id carries no version hash"
    if current == recorded:
        return FRESH, ""
    other_family = "bitstream" if family == "document" else "document"
    try:
        other = (_document_hash(document) if other_family == "document"
                 else _bitstream_hash(document, mss_index))
    except Exception:
        other = ""
    if other and other == recorded:
        return FRESH, (f"{row.declared_name}: pin is current, but it records the "
                       f"{other_family} hash while kind {row.kind!r} declares {family} — "
                       "the row's kind is mis-declared, not its pin")
    subject = "the document is" if family == "document" else "the closure hashes to"
    return STALE, (f"{row.declared_name}: pinned {recorded[:8]}… but {subject} "
                   f"{current[:8]}… now — re-pin the row")
