"""Instance identity: which msn a sandbox is keyed on, and what instances exist.

An instance is a scoped view of the store keyed on ``msn_id``. Its msn is a
property of its data — the msn its own documents already carry — and is
discovered, never computed.

THE RULE: never derive meaning by parsing msn segments. An msn is a hierarchical
path like a domain name, and a label's meaning is parent-dependent: under
``-77-`` segment 6 is an organisational tier, but under ``-66-`` the same
position is geography. Reading a segment in isolation tells you nothing. The
authority for "which entity owns this sandbox" is ``registrar.legal_entity``;
the authority for "which msn is this sandbox keyed on today" is the sandbox's
own documents. This module answers the second question. The two agreeing is an
invariant worth checking (see ``fnd_app/scripts/rekey_sandbox_msn.py``), not an
assumption to build on.

Pure functions over a document list — every input is already-read data, so this
stays in ``micyte.core`` with no adapter dependency. Callers do the I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from micyte.core.document_naming import (
    ANCHOR_DOCUMENT_NAMES,
    CanonicalNameError,
    parse_canonical_document_id,
)
from micyte.core.instance_baseline import MSN_PROFILE_DOCUMENT

# A sandbox is a farm instance when it has an ANCHOR and this profile. Shape, not a list:
# a farm onboarded tomorrow is discovered with no code change. This generalizes
# micyte/tools/agronomics_viewer.py::_list_farms.
#
# The anchor half used to be the literal `"anchor"`, which was true while that was the only
# name an anchor could have. A system sandbox's anchor is named `anthology`, and every
# instance now keeps its core sandbox in `system` — so that literal would have quietly
# stopped recognising farms the day they moved, taking is_farm, home_sandbox, the instance
# sort order, default_farm_sandbox and agronomics eligibility with it. The anchor is asked
# about through ANCHOR_DOCUMENT_NAMES, which the naming contract owns.
FARM_PROFILE_DOCUMENT = "farm_profile"

# A sandbox is a hosted-channel sandbox when it has an anchor and this marker — the
# positive kind marker the hosted-channel convention (2026-08-02 §2c) requires.
# A channel is never inferred from what it lacks.
CHANNEL_PROFILE_DOCUMENT = "channel_profile"

# `MSN_PROFILE_DOCUMENT` is imported from `instance_baseline`, which DECLARES it as the
# floor's first entry, rather than restated here — the two must be the same document or
# this module's shape test recognises something the baseline does not provision.
#
# It is the second half of the instance shape, beside the anchor. An anchor alone is not
# enough: an app sandbox is anchored from the moment `bootstrap_app_sandbox` copies one,
# and so is a channel, a taxonomy and the archetype library. Provisioning is what writes
# the profile, so the profile is what "provisioned" can be asked about.

# The document only a directory keeper holds: the network registry itself. The
# registrar carries an ``anchor`` AND a document named ``farm_profile`` — because
# it KEEPS other entities' profiles — so the farm shape alone classifies it as a
# farm (live consequence: ``default_farm_sandbox()`` returned ``"registrar"``).
# A farm describes itself; a directory describes everyone else. Holding the
# registry is what separates them.
REGISTRY_DOCUMENT = "registry"

# The core sandbox an instance keeps its own documents in, and the one it opens on when
# it is not a farm. A structural name (like FARM_PROFILE_DOCUMENT), not a tenant's name —
# which is why every instance can hold one: they are told apart by msn, not by name.
SYSTEM_SANDBOX = "system"

# Where "which entity owns this msn" is answered. The registrar is the authority —
# the DNS of the network — and the only correct way to attach meaning to an msn.
REGISTRAR_SANDBOX = "registrar"
LEGAL_ENTITY_DOCUMENT = "legal_entity"
# legal_entity rows serialize as flat (value, "rf.x-y-z") pairs, value first.
MSN_FIELD = "rf.3-1-3"
SLUG_FIELD = "rf.3-1-13"

# Words that read wrong under a plain title-case: legal suffixes ("Llc") and
# acronyms ("Fnd Ebi"). A rule about how WORDS render — deliberately not a
# registry of sandboxes or entities. Adding a farm must never require touching
# this; adding an acronym is the only reason to.
_WORD_RENDERINGS: dict[str, str] = {
    "llc": "LLC",
    "inc": "Inc",
    "lp": "LP",
    "co": "Co",
    "fnd": "FND",
    "ebi": "EBI",
    "cts": "CTS",
    "gis": "GIS",
    "txa": "TXA",
    "lcl": "LCL",
}


def prettify_token(token: str) -> str:
    """``a_sandbox_token_llc`` -> ``A Sandbox Token LLC``."""
    return " ".join(_WORD_RENDERINGS.get(word, word.title()) for word in (token or "").split("_") if word)


@dataclass(frozen=True)
class SandboxInstance:
    """A sandbox present in the store, and the msn it is keyed on."""

    sandbox: str
    msn_id: str
    document_names: frozenset[str]

    @property
    def is_directory_keeper(self) -> bool:
        """This sandbox holds the network registry — profiles OF others, not its own."""
        return REGISTRY_DOCUMENT in self.document_names

    @property
    def has_anchor(self) -> bool:
        """Whether this sandbox is anchored, whatever its anchor is CALLED.

        `anchor` in most sandboxes, `anthology` in a system sandbox. Both names are
        reserved for anchors and for nothing else, so asking about the pair is the same
        question as asking about the flag — and it survives an instance moving its
        documents into `system`, which asking about one literal does not.
        """
        return bool(self.document_names & ANCHOR_DOCUMENT_NAMES)

    @property
    def is_farm(self) -> bool:
        """Shape alone. The `not is_directory_keeper` clause this used to carry existed
        because `registrar` held a document named `farm_profile` — it was compensating for
        a mislocated document, not expressing a rule. Phase 3b moved that document to
        `agnet/member_profiles` (renamed, so the CHANNEL does not trip the farm shape
        either), and the exception went with it. A sandbox is a farm when it looks like
        one."""
        return self.has_anchor and FARM_PROFILE_DOCUMENT in self.document_names

    @property
    def is_channel(self) -> bool:
        """A hosted-channel sandbox, identified by its own kind marker."""
        return self.has_anchor and CHANNEL_PROFILE_DOCUMENT in self.document_names

    @property
    def is_instance_core(self) -> bool:
        """This is an instance's OWN core sandbox — the thing provisioning makes.

        Shape, like `is_farm` and `is_channel`, and for the same reason: a sandbox named
        `system` is one on every instance at once, so the name cannot say. What separates
        a core sandbox from every other anchored sandbox is that it carries the
        instance's profile of ITSELF.

        Anchor alone is not the question. Measured on the live store 2026-08-27: of 19
        anchored sandboxes only 8 hold `msn_profile`, and the other 11 are app sandboxes,
        channels, the taxonomy and the archetype library — none of them somewhere to log
        in.
        """
        return self.has_anchor and MSN_PROFILE_DOCUMENT in self.document_names


def _parsed(documents: Iterable[Any]) -> Iterator[Any]:
    """Yield the parsed id of every canonically-named document, skipping the rest."""
    for document in documents:
        try:
            yield parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
        except CanonicalNameError:
            continue


def sandbox_msn_id(documents: Iterable[Any], sandbox: str) -> str | None:
    """The msn ``sandbox``'s documents are keyed on.

    ``None`` when the sandbox has no documents (nothing to discover from) or when
    more than one msn uses that sandbox NAME — the caller must not guess which.

    That second case used to mean only "a split-brain sandbox mid-rekey". It now also
    means the ordinary case: every instance keeps its own core sandbox named ``system``,
    so the name alone stops identifying one. Callers that know their instance should pass
    ``msn_id``; callers that cannot must handle ``None`` rather than pick a winner.
    """
    found = {p.msn_id for p in _parsed(documents) if p.sandbox == sandbox and p.msn_id}
    return found.pop() if len(found) == 1 else None


def list_sandbox_instances(documents: Iterable[Any]) -> list[SandboxInstance]:
    """Every sandbox in the store, keyed on ``(msn_id, sandbox)``.

    A sandbox's address is the PAIR. It used to be grouped by name alone, with any
    sandbox whose documents carried more than one msn omitted rather than guessed at —
    a rule written when a name identified exactly one sandbox, so two msns under one name
    could only be a rekey caught halfway.

    That is no longer what it means. Every instance holds its own core sandbox named
    ``system``, so grouping by name collapsed all of them onto one key and the
    disagreement rule then dropped the lot: measured on stub documents, four instances
    each naming their sandbox ``system`` yielded ZERO sandbox instances and an empty
    portal switcher.

    Keyed on the pair, there is nothing left to guess: each entry is one msn's sandbox,
    holding exactly the documents that msn keyed there. A genuinely half-rekeyed sandbox
    now shows up as two entries — its documents really do belong to two msns, and saying
    so is more honest than making the sandbox disappear.
    """
    names: dict[tuple[str, str], set[str]] = {}
    for p in _parsed(documents):
        if not p.sandbox or not p.msn_id:
            continue
        names.setdefault((p.msn_id, p.sandbox), set()).add(p.name)
    out = [
        SandboxInstance(sandbox=sandbox, msn_id=msn, document_names=frozenset(ns))
        for (msn, sandbox), ns in names.items()
    ]
    # Sorted by the whole address, so the order is stable when a name repeats.
    out.sort(key=lambda i: (i.sandbox, i.msn_id))
    return out


def list_farm_instances(documents: Iterable[Any]) -> list[SandboxInstance]:
    """The sandboxes that are farms, by shape (``anchor`` + ``farm_profile``)."""
    return [i for i in list_sandbox_instances(documents) if i.is_farm]


def _row_fields(row: Any) -> dict[str, Any]:
    raw = row.raw if isinstance(row.raw, list) else [row.raw]
    flat = raw[0] if raw and isinstance(raw[0], list) else raw
    return {str(flat[i + 1]): flat[i] for i in range(0, len(flat) - 1, 2)}


class DocumentRowsRequired(RuntimeError):
    """A rows-free summary reached a reader in this module that must see ROWS.

    Raised rather than reading a document's rows with a ``()`` default, which yields
    nothing for a summary and is indistinguishable from a genuinely empty document.
    That silence is not hypothetical: once the shell began reading the rows-free
    document index, a summary ``agnet.accounts`` read as "nobody is engaged",
    ``list_portal_instances`` filtered EVERY instance out, and the instance switcher
    rendered nothing at all — on a store with three instances.
    """


def _rows_of(document: Any) -> tuple[Any, ...]:
    """``document.rows``, refusing a rows-free summary. See ``ROWS_REQUIRED_DOCUMENTS``.

    ``()`` is a real answer (a document with no rows); a missing attribute is not.
    """
    rows = getattr(document, "rows", None)
    if rows is None:
        raise DocumentRowsRequired(
            f"{getattr(document, 'document_id', '<unknown>')} carries no rows. "
            "A caller reading from a document INDEX must load every document in "
            "ROWS_REQUIRED_DOCUMENTS in full."
        )
    return tuple(rows)


def _find_legal_entity(documents: Iterable[Any]) -> Any | None:
    """The single ``registrar.legal_entity`` document, or ``None``."""
    for document in documents:
        try:
            parsed = parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
        except CanonicalNameError:
            continue
        if parsed.sandbox == REGISTRAR_SANDBOX and parsed.name == LEGAL_ENTITY_DOCUMENT:
            return document
    return None


def _slug_for_msn(legal_entity: Any, msn_id: str) -> str | None:
    """The entity slug ``legal_entity`` binds to ``msn_id`` — scans its rows only.

    ``None`` when the registrar does not know the msn, or binds it ambiguously.
    """
    slugs = {
        str(fields.get(SLUG_FIELD))
        for row in _rows_of(legal_entity)
        if (fields := _row_fields(row)).get(MSN_FIELD) == msn_id and fields.get(SLUG_FIELD)
    }
    return slugs.pop() if len(slugs) == 1 else None


def registrar_entity_slug(documents: Iterable[Any], msn_id: str) -> str | None:
    """The entity slug ``registrar.legal_entity`` binds to ``msn_id``.

    This is the resolution step: an msn means whatever the registrar says it
    means. ``None`` when the registrar does not know the msn, or binds it
    ambiguously — in which case the caller must not invent a name for it.

    Resolving many msns at once? Find the legal_entity once (``_find_legal_entity``)
    and call ``_slug_for_msn`` per msn — this convenience re-scans for it each call.
    """
    legal_entity = _find_legal_entity(documents)
    return _slug_for_msn(legal_entity, msn_id) if legal_entity is not None else None


@dataclass(frozen=True)
class PortalInstance:
    """One msn, and every sandbox keyed on it.

    This is the unit the profile switcher switches between: "which MiCyte portal
    am I in". FND owns several sandboxes under one msn; a farm owns one.
    """

    msn_id: str
    sandboxes: tuple[SandboxInstance, ...]
    entity_slug: str | None
    #: The title the instance gives ITSELF, from its own `msn_profile`. Empty when the
    #: instance has not been established — see :meth:`label` for what that costs.
    profile_title: str = ""

    @property
    def is_farm(self) -> bool:
        return any(s.is_farm for s in self.sandboxes)

    @property
    def is_provisioned(self) -> bool:
        """Does this msn hold a CORE sandbox — the thing provisioning makes?

        What makes an msn somewhere to log in, and the whole definition of an instance
        for this module. `provision_instance` creates exactly this: an anchored sandbox
        with the baseline documents beside it, `msn_profile` first. An msn that merely
        appears somewhere in the corpus is a party in somebody's directory.

        Asked through :attr:`SandboxInstance.is_instance_core`, so the ANCHOR half knows
        the reserved pair (a core sandbox's anchor is named `anthology` and a non-core
        one's is `anchor`; the live store carries both spellings in `system` sandboxes,
        so a literal would have recognised five of eight) and the PROFILE half is what
        tells a core sandbox from the eleven other anchored ones.

        It asks about ANY core sandbox and not about one named `system`, which was the
        first version of this and was too narrow by exactly the history it forgot: every
        instance keeps its core in `system` NOW, and the farms predate that — their core
        sandbox carries the farm's own name. A predicate that names a sandbox is one
        rename away from being wrong, which is the same lesson `has_anchor` records about
        the literal `"anchor"`.
        """
        return any(s.is_instance_core for s in self.sandboxes)

    @property
    def home_sandbox(self) -> str:
        """The sandbox the portal opens on when this instance is selected."""
        farms = sorted(s.sandbox for s in self.sandboxes if s.is_farm)
        if farms:
            return farms[0]
        names = sorted(s.sandbox for s in self.sandboxes)
        return SYSTEM_SANDBOX if SYSTEM_SANDBOX in names else names[0]

    @property
    def core_sandbox(self) -> str | None:
        """The sandbox name this instance's own profile lives in, or ``None``."""
        cores = sorted(s.sandbox for s in self.sandboxes if s.is_instance_core)
        return cores[0] if cores else None

    @property
    def label(self) -> str:
        """Human label — what the instance CALLS ITSELF, else a fallback.

        The order is the direction identity travels (operator, 2026-08-26): an instance is
        established, and only then reports its profile to the registrar, "and that's only
        even really relevant to contact between instances". So its own `msn_profile` is
        asked first and the registrar is the fallback, not the source.

        It ran the other way round until 2026-08-27 and the switcher showed it: the
        registrar binds three of eight msns, so five rows resolved to no slug, fell
        through to the home sandbox — named `system` on every one of them — and the
        profile page listed **"System" five times**, five different instances wearing one
        name. Reversing the order does not by itself fix that; it makes the fix possible,
        because the document that can tell them apart is the one each instance holds.

        `profile_title` is human text an instance wrote about itself ("Boutique Homes
        NEO"), so it is NOT put through `prettify_token` — that renders a snake_case slug
        and would take "Kai Kurokawa" apart. The two fallbacks are tokens and still are.
        """
        return self.profile_title or prettify_token(self.entity_slug or self.home_sandbox)


#: The documents this module reads ROWS from, as ``(sandbox, name)``. ``""`` as the
#: sandbox means ANY sandbox — see :func:`rows_required`.
#:
#: Every other question it answers — which sandboxes exist, which msn each is keyed on,
#: which are farms, which are core — is document IDENTITY, which a rows-free index
#: already carries. These two are the exceptions, and they are the two halves of an
#: instance's name: what it calls ITSELF, and what the registrar calls it.
#:
#: They are named HERE, beside the readers, rather than in the caller — so a rows-read
#: added below is an entry added here, and the caller cannot silently fall behind it.
#: Loading only ``legal_entity`` is exactly how the switcher went empty.
#:
#: It named a hosted CHANNEL's roster and lcl until 2026-08-27, which is what
#: `engaged_msns` read (see :func:`list_portal_instances`). Two costs went with them:
#: a full-document read of the largest of the three on every catalog open, and — because
#: the entry named both local-domain spellings while the store holds one — a ``wanted``
#: set that never emptied, so the caller's early exit never fired and it scanned all 776
#: index entries every request.
ROWS_REQUIRED_DOCUMENTS: frozenset[tuple[str, str]] = frozenset(
    {
        (REGISTRAR_SANDBOX, LEGAL_ENTITY_DOCUMENT),
        ("", MSN_PROFILE_DOCUMENT),
    }
)


def rows_required(sandbox: str, name: str) -> bool:
    """Does this document need its ROWS loaded before this module reads it?

    A PREDICATE and not a set membership test, because the two entries differ in kind and
    a caller matching pairs literally gets the second one wrong. ``legal_entity`` is one
    document in one sandbox. ``msn_profile`` is one document PER INSTANCE, all eight of
    them in a sandbox named ``system`` — so a caller that stops at the first match loads
    one instance's profile and leaves seven rows-free, and every one of those seven then
    falls back to a name.

    That is the same shape as the read this replaced, one layer down: a check that covers
    a subset reads as complete. Callers must load EVERY document this returns true for.
    """
    return (sandbox, name) in ROWS_REQUIRED_DOCUMENTS or ("", name) in ROWS_REQUIRED_DOCUMENTS


def _profile_titles(documents: Iterable[Any]) -> dict[str, str]:
    """``msn_id -> the title each instance gives ITSELF``, from its own ``msn_profile``.

    Resolved through the namespace CLAIMED for the pair ``(msn, sandbox)``, never through
    the sandbox name. Every instance's core sandbox is named ``system`` and the three
    namespaces in play disagree about where ``title`` sits — ``3-1-3`` under `registrar`,
    ``3-1-5`` under `system`, ``3-1-2`` under `farm`. Reading all eight under one
    numbering would not error; it would return each instance a cell belonging to some
    other field, which is the failure a wrong namespace always has.

    Absences are silent on purpose: an instance that has not been established yet has an
    empty profile, and :meth:`PortalInstance.label` says what happens then.
    """
    from micyte.core.datum_ops import archetype_shape as _ash
    from micyte.core.datum_ops import field_registry as fr
    from micyte.core.datum_ops.datum_resolve import as_text, decode_label, iter_marker_pairs

    out: dict[str, str] = {}
    for document in documents:
        try:
            parsed = parse_canonical_document_id(str(getattr(document, "document_id", "") or ""))
        except CanonicalNameError:
            continue
        if parsed.name != MSN_PROFILE_DOCUMENT or not parsed.msn_id:
            continue
        try:
            namespace = fr.namespace_for_sandbox(parsed.sandbox, msn_id=parsed.msn_id)
        except KeyError:
            continue
        for row in _rows_of(document):
            for marker, magnitude in iter_marker_pairs(_ash._row_head(row.raw)):
                if _ash._field_name(as_text(marker), sandbox=namespace) != "title":
                    continue
                title = decode_label(magnitude).strip()
                if title:
                    out.setdefault(parsed.msn_id, title)
    return out


def list_portal_instances(documents: Iterable[Any]) -> list[PortalInstance]:
    """Every portal instance in the store, keyed by msn.

    Farms sort last so the operator's own instance leads, then alphabetically —
    an ordering rule, so no instance is privileged by being named in code.
    """
    documents = list(documents)
    # Resolve the registrar's legal_entity document ONCE (a full-corpus scan);
    # each instance's slug is then a small scan of that one document's rows,
    # instead of re-scanning the whole corpus per msn.
    legal_entity = _find_legal_entity(documents)
    titles = _profile_titles(documents)
    by_msn: dict[str, list[SandboxInstance]] = {}
    for instance in list_sandbox_instances(documents):
        by_msn.setdefault(instance.msn_id, []).append(instance)
    out = [
        PortalInstance(
            msn_id=msn,
            sandboxes=tuple(sorted(sandboxes, key=lambda s: s.sandbox)),
            entity_slug=_slug_for_msn(legal_entity, msn) if legal_entity is not None else None,
            profile_title=titles.get(msn, ""),
        )
        for msn, sandboxes in by_msn.items()
    ]
    # An instance is an msn that has been PROVISIONED — see `is_provisioned`.
    #
    # This filtered on `engaged_msns` until 2026-08-27, which read ONE hosted channel's
    # membership roster and made that channel's constant, `ENGAGEMENT_CHANNEL`, the
    # definition of instancehood. Two things were wrong with it and only one was visible:
    #
    #   * the roster held four rows and the store held eight instances, so five real
    #     client instances could not be switched to at all;
    #   * the channel it named is one specific channel still under development, and its
    #     name is a legacy one. Whether a conservancy, a musician or an actor has a place
    #     in an agricultural network is not the question "is this somewhere to log in",
    #     and a channel must never be the one that answers a general question.
    #
    # The case it was built for is still handled, and handled where it belongs: an account
    # nobody has taken up has no core sandbox, so it is not provisioned and does not
    # appear. That is true of the farm instance this filter was added to hide — retired at
    # the operator's instruction, and measured 2026-08-27 it holds no documents at all.
    #
    # The roster remains the channel's own fact, read by the channel's own surfaces. It is
    # simply not what decides this, and the readers for it are gone from this module.
    out = [i for i in out if i.is_provisioned]
    out.sort(key=lambda i: (i.is_farm, i.label))
    return out


def default_farm_sandbox(documents: Iterable[Any]) -> str | None:
    """The farm to show when the caller has not chosen one.

    The first farm in a stable alphabetical order — a rule, not a name. ``None``
    when the store holds no farm, because inventing one would claim a farm exists
    where none does. Callers must handle ``None`` rather than substitute a
    literal.
    """
    farms = list_farm_instances(documents)
    return farms[0].sandbox if farms else None
