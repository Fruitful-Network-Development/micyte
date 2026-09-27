"""Site hosting port — the served tree a grantee's site is, and the edits that reach it.
CONTRACT ONLY.

The Design tab has always written straight to disk: `site_content_extension` replaces a
string in the site's SOURCE — a manifest JSON for FND and CVCC, a `.html` file for TFF and
BPW — and re-renders where the site is manifest-driven. That works, and it is the one
write path in this stack with no port in front of it, so nothing about it is declared,
nothing about it can be granted separately, and the Ports surface cannot show it at all.

Declared here so that changes to a CLIENT'S PUBLIC SITE are governed the way mail and
payment already are. No peripheral, no route and no filesystem call: `micyte` holds none.
An implementation lives host-side and judges the operation inside the function that opens
the tree.

Five operations, at the grain worth withholding
-----------------------------------------------
An operation is what an operator would refuse SEPARATELY, and these five differ in what
a mistake costs:

* :data:`OPERATION_PAGE_LIST` — which pages exist, which parts are editable, and which
  assets are on offer. Discloses the shape of somebody's site and nothing else; it is the
  one an operator would grant to let a client LOOK.
* :data:`OPERATION_CONTENT_REPLACE` — one ``{old, new}`` pair applied to the source. This
  is the operation that changes what a stranger reads. Guarded at the implementation by
  exactly-one-occurrence, because an ambiguous replacement is the difference between an
  edit and a corruption — but the guard is a correctness rule and this is the permission.
* :data:`OPERATION_ASSET_SWAP` — point an image on a page at a different file the site
  already has. Its own operation because its fence is its own: the target must be in the
  site's gallery, where a content replacement could point an ``<img>`` anywhere.
* :data:`OPERATION_ASSET_UPLOAD` — new bytes at a public URL. Deliberately NOT the same
  operation as a replacement: swapping a word changes what the site says, while adding a
  file changes what the site SERVES, and the second is how a site comes to host something
  nobody reviewed. "Edit the copy" and "put a file on the internet" are one permission
  only if nobody writes down the difference — the ``send``/``forward`` distinction the
  email port already makes, one layer out.

* :data:`OPERATION_ARTICLE_PUBLISH` — a written piece stored as a leaflet, and the pages
  rebuilt so it is reachable. It is neither of the two above and the difference is worth
  a grant of its own: a replacement changes words on a page that already exists, an upload
  leaves a file the site may or may not link to, and this **gives somebody a new address on
  the internet** and puts a tile on a gallery pointing at it. An operator might well let a
  client fix a typo without letting them add pages.
* :data:`OPERATION_ARTICLE_RETIRE` — take one back down, with the pages rebuilt again.
* :data:`OPERATION_ARTICLE_SEND` — the same written piece put in the inboxes of the people
  who asked for it. The sharpest version of the distinction this list keeps making: a
  publish and a retire are the same words moving on and off a page the author controls,
  and a send leaves that control entirely. Thirty-eight people have it and there is no
  taking it back.

Why this port HAS a delete when the sentence here used to say it does not
------------------------------------------------------------------------
Until 2026-08-26 this docstring read: *"There is no delete. The Design surface performs
none, and an operation nothing performs is a permission an operator would have to reason
about with no way to exercise it."* That was a true statement about the iframe Design
editor, which swaps images and replaces strings and removes nothing.

It is not true of authoring. ``article_authoring.delete_article`` exists and is wired to a
live route, and the retitle path retires the PRIOR slug on every title edit — so a publish
operation that could not retire would strand the old page, its gallery tile and its sitemap
entry the first time somebody renamed a piece. Retiring is performed, therefore it is
declared. The rule the old paragraph stated is intact; what changed is which side of it
this port stands on.

Listing what has been published is NOT a fourth read. It is
:data:`OPERATION_PAGE_LIST` — "which pages exist" — asked about the pages authoring made.
Giving it its own operation would let an operator grant one and withhold the other while
both answer the same question, which is how two permissions come to disagree.

The SERVICE token
-----------------
:data:`SERVICE_LOCAL_TREE` is what a DIRECT adapter carries: the served tree on this host,
written in place. A hosted CMS or an object store filling the same seam carries its own,
because a grant over one is never a grant over another.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: A leaflet's name carries its date as a segment, so the shape is the port's business.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: What pages and assets a site has, and which parts of them are editable.
OPERATION_PAGE_LIST = "page.list"

#: One `{old, new}` pair applied to the site's source. Changes what a stranger reads.
OPERATION_CONTENT_REPLACE = "content.replace"

#: New bytes at a public URL. Changes what the site SERVES, which is not the same act.
OPERATION_ASSET_UPLOAD = "asset.upload"

#: Point an image already ON a page at a different file the site ALREADY has.
#:
#: A THIRD operation rather than a use of the two above, because it is a third act. An
#: upload adds bytes the site did not serve; a content replacement changes any string it
#: likes; this changes which existing picture a page shows, and the set it may choose from
#: is the site's own gallery. That last part is the reason it cannot be folded into
#: `content.replace`: the swap path REFUSES a target that is not in the gallery
#: (`'{new}' is not in your {kind} gallery`), and reaching the same file through a string
#: replacement would point an `<img>` anywhere at all. Same bytes on the page, no fence.
#:
#: Reachable from nothing until 2026-08-31. `save_site_content` has carried a `swaps`
#: channel beside `edits` since the legacy design tab drove it, and no port operation ever
#: called it — the gallery check was written, correct, and unreachable.
OPERATION_ASSET_SWAP = "asset.swap"

#: A written piece, and the pages rebuilt so it is reachable. Adds a PAGE, which neither
#: a replacement nor an upload does.
OPERATION_ARTICLE_PUBLISH = "article.publish"

#: Take a published piece back down. Declared because it is performed — see the docstring.
OPERATION_ARTICLE_RETIRE = "article.retire"

#: Put a written piece in the inboxes of the people who asked for it.
#:
#: SEPARATE FROM `article.publish`, and the grain is the argument — the same argument
#: `asset.swap` makes against `content.replace`. A publish puts words on a page the author
#: can take back down in a minute. A send puts them in 38 people's mail and there is no
#: taking it down: no edit, no retraction, no second thought. Those are not one permission
#: that happens to have two buttons.
#:
#: So an operator can hand a client the whole of writing for the web and withhold the list
#: — or the reverse, for a client who mails and does not blog — and the tab shows only
#: what the grant allows.
#:
#: This DELIBERATELY crosses a line recorded in `instance_account.newsletter_facts`, that
#: "a newsletter surface that could dispatch would cross exactly the line the operator
#: drew". The operator lifted it on 2026-09-13, for the three instances that have a list.
#: It is crossed HERE, as a named permission on a surface an operator can see and revoke,
#: rather than inside a code path with a comment — which is the whole difference between
#: a line that moved and a line that leaked.
OPERATION_ARTICLE_SEND = "article.send"

#: A month of the site's traffic, counted. READ-ONLY and separately withholdable: it is
#: the only operation on this port that touches nobody's words, and the only one an
#: unattended routine performs — so an operator who wants analytics folded in nightly
#: without letting a job publish grants exactly this and nothing else.
OPERATION_ANALYTICS_READ = "analytics.read"

#: Rewrite a PROFILE the site's pages are generated from: which photograph stands for the
#: thing, the order (and hiding) of the rest, and its short and long descriptions.
#:
#: Its own operation, and the grain is the argument. `content.replace` changes one string
#: on one page; `asset.swap` points one <img> at another file. This edits the LEAFLET —
#: the source of record several pages are built from — and then rebuilds them, so a single
#: save can change a hero, a card, a project row and an overlay at once, and can take a
#: photograph off the site without deleting it. "May arrange and describe their own
#: projects" is a different thing to grant from "may rewrite any text on the page", and an
#: operator may well permit the first and withhold the second. The read half — which
#: profiles the site allocates and what each holds — is disclosed under
#: :data:`OPERATION_PAGE_LIST`, for the reason the module docstring gives about articles:
#: it answers "what does this site carry", asked about the leaflets.
#:
#: Operator, 2026-09-10: "I want a user of the Enchir application to be able to edit the
#: project profile, selecting how the images are ordered or how the profile is drafted
#: (description short and or long etc)".
OPERATION_PROFILE_EDIT = "profile.edit"
#: Write a PROJECT DOCUMENT's view beside the site's assets and derive the profile the pages
#: are generated from — the instance's books become the source and the leaflet a copy
#: (TASK-2026-09-11-001 P2, docs/wiki/44-project-documents.md). Its own permission because
#: it lands files (the view, pictures the pool lacks) AND rewrites a profile.
OPERATION_PROJECT_EXPORT = "project.export"

#: The served tree on this host, written in place — what a direct adapter binds.
SERVICE_LOCAL_TREE = "local_tree"


class SiteHostingError(ValueError):
    """The site, or the edit, is not one this seam can act on."""


class SiteHostingUnavailable(SiteHostingError):
    """The tree is unreachable — distinct from an edit being refused.

    Kept separate for the reason the email port keeps its own: "the provider is down" and
    "you may not do that" are different facts, and folding a refusal into an outage sends
    an operator to fix the wrong thing.
    """


class AmbiguousEdit(SiteHostingError):
    """The `old` value does not occur EXACTLY once in the source.

    Zero occurrences and several are both refused, and refused the same way: an edit that
    matched nothing did not happen, and an edit that matched twice changed something the
    caller did not look at. Neither is an outage and neither is a permission problem,
    which is why this is its own error rather than a bare failure.
    """


@dataclass(frozen=True)
class EditablePage:
    """One page of a site, as the picker describes it."""

    path: str
    title: str = ""
    editable: bool = False
    kind: str = ""            # `manifest` or `static` — what the source IS
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.path or "").strip():
            raise SiteHostingError("a page needs a path")


@dataclass(frozen=True)
class AssetSwap:
    """One image on one page, pointed at a different file the site already has.

    ``kind`` names which gallery the target must be in (`image`, `icon_file`,
    `icon_sprite`); the store refuses a `new` that is not in it, which is the fence that
    makes this its own operation rather than a content replacement.

    `old` is the value ON the page — the `src` as the page's source spells it — and `new`
    is the gallery entry to put there. Both are required for the reason `ContentEdit` gives
    about an empty `old`: a swap with nothing to match is not a swap.
    """

    page: str
    old: str
    new: str
    kind: str = "image"

    def __post_init__(self) -> None:
        if not str(self.page or "").strip():
            raise SiteHostingError("a swap needs a page")
        if not str(self.old or ""):
            raise SiteHostingError(
                "a swap needs the OLD value: the image currently on the page")
        if not str(self.new or ""):
            raise SiteHostingError("a swap needs the NEW image")
        if self.old == self.new:
            raise SiteHostingError("a swap that changes nothing is not a swap")


@dataclass(frozen=True)
class ContentEdit:
    """A single `{old, new}` replacement against a page's source."""

    page: str
    old: str
    new: str

    def __post_init__(self) -> None:
        if not str(self.page or "").strip():
            raise SiteHostingError("an edit needs a page")
        if not str(self.old or ""):
            raise SiteHostingError(
                "an edit needs the OLD value: a replacement with nothing to match is an "
                "append wearing an edit's name")
        if self.old == self.new:
            raise SiteHostingError("an edit that changes nothing is not an edit")


@dataclass(frozen=True)
class ArticleDraft:
    """One written piece as an author hands it over.

    The body is MARKDOWN and the title is the first ``# `` line in it — there is no title
    field, because a piece whose heading and whose title can disagree has two titles. The
    slug follows from the title, so a retitle MOVES the piece; :attr:`prior_slug` is how
    the caller says which piece was being edited so the old one can be retired instead of
    left behind as a duplicate.

    Nothing here caps the body. The 4096-character budget belongs to a MOS writing
    (``note_books.NOTE_CHAR_BUDGET``) and does not apply: a piece is stored as a leaflet,
    whose interior this port hands over whole. Measured 2026-08-26, 27 of the 33 live
    articles exceed that budget and 12 use characters the writing substrate refuses
    outright, so reading the limit across from notes would truncate real work.
    """

    body: str
    date: str = ""            # YYYY-MM-DD; empty means the implementation's today
    subtopic: str = ""
    summary: str = ""
    hidden: bool = False
    prior_slug: str = ""      # the piece being edited, when a retitle moves the slug

    def __post_init__(self) -> None:
        if not str(self.body or "").strip():
            raise SiteHostingError(
                "a draft needs a body: publishing nothing would still add a page")
        date = str(self.date or "").strip()
        if date and not _DATE_RE.match(date):
            raise SiteHostingError(
                f"date {date!r} is not YYYY-MM-DD; the date is a SEGMENT of the leaflet "
                "name, so a loose one becomes an unaddressable file")


@dataclass(frozen=True)
class PublishedArticle:
    """One piece as the site now carries it — what a publish returns and a listing lists."""

    slug: str
    title: str = ""
    date: str = ""
    subtopic: str = ""
    hidden: bool = False
    url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.slug or "").strip():
            raise SiteHostingError("a published piece needs a slug — it is its address")


@dataclass(frozen=True)
class SentNewsletter:
    """What a send actually DID, counted — because the count is the only receipt.

    A publish can be checked by loading the page. A send cannot be checked at all: the
    messages are gone, and the only account of where they went is the one the dispatch
    kept. So this carries four separate numbers rather than a success word.

    :attr:`target_count` is who it was ADDRESSED to and the other three are what became of
    them. They are kept apart because the two transports answer at different times: the
    queue path hands every recipient to a Lambda and reports them ``queued``, with terminal
    status arriving later on the dispatch callback, while the direct path sends each one
    now and reports ``sent`` or ``failed`` immediately. Folding queued into sent would
    report delivery this port has not yet been told about.

    :attr:`slug` is the ARTICLE's slug, not a second one minted for the mail. A piece that
    is posted and then sent is one piece, and giving the send its own address is how the
    two halves of it stop being findable from each other.
    """

    slug: str
    subject: str = ""
    transport: str = ""
    target_count: int = 0
    queued_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    dispatch_id: str = ""
    sent_at: str = ""

    def __post_init__(self) -> None:
        if not str(self.slug or "").strip():
            raise SiteHostingError(
                "a sent piece needs a slug — it is what makes a second send of the same "
                "writing recognisable as a repeat rather than a new issue")


@dataclass(frozen=True)
class SiteProfile:
    """One profile the site allocates, as the leaflet states it.

    ``gallery_refs`` is the ORDERED gallery, hidden entries included — an image keeps its
    place while withheld, so unhiding it restores it in place rather than at the end.
    ``gallery_hidden_refs`` is the subset the site does not show. ``feature_ref`` is the
    one picture that stands for the thing; ``""`` means the leaflet has not chosen and the
    site falls back to the first shown photograph. ``bio`` is the long description as
    paragraphs; ``summary`` the short one.
    """

    slug: str
    name: str = ""
    kind: str = ""                 # the leaflet's `profile_kind` (home, legal_entity, …)
    status: str = ""               # `listing_status` for a home; whatever the kind keeps
    feature_ref: str = ""
    gallery_refs: tuple[str, ...] = ()
    gallery_hidden_refs: tuple[str, ...] = ()
    #: ``ref -> the name a person calls that photograph by``. The implementation derives
    #: it from the gallery and accepts it back in a :class:`ProfileEdit`, so a form can
    #: show ``fireplace.avif`` and send it, and nobody retypes a pool path.
    gallery_names: dict[str, str] = field(default_factory=dict)
    gallery_titles: dict[str, str] = field(default_factory=dict)
    summary: str = ""
    bio: tuple[str, ...] = ()
    url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.slug or "").strip():
            raise SiteHostingError("a profile needs a slug")

    def name_of(self, ref: str) -> str:
        """The readable name for ``ref``, or the ref itself."""
        return self.gallery_names.get(ref) or ref


@dataclass(frozen=True)
class ProjectPicture:
    """One picture a project document names: its SLOT on the instance's tree, the sha256
    its `art.` document carries (the artifact's identity — the pool file with the same
    bytes hashes the same), a name for a file the pool lacks, and a loader that decodes
    the bytes only when the site needs them written."""

    slot: str
    sha256: str
    name: str = ""
    bytes_loader: Any = None


@dataclass(frozen=True)
class ProjectExport:
    """A project document's view, offered to the site: ``slug`` names the profile the
    site's pages are generated from, ``view`` is `ProjectView.to_dict()` (the expected
    keys; roles and kinds by label), ``pictures`` the slots the view names."""

    slug: str
    view: dict[str, Any]
    pictures: tuple[ProjectPicture, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.slug or "").strip():
            raise SiteHostingError("a project export needs the profile's slug")
        if not isinstance(self.view, dict) or not self.view:
            raise SiteHostingError("a project export needs the document's view")


@dataclass(frozen=True)
class ProfileEdit:
    """What to change on one profile. ``None`` means "leave it as it is".

    Every field is optional and at least one must be given — an edit that names a profile
    and changes nothing about it is refused for the reason `ContentEdit` refuses
    ``old == new``: it would report a save over a leaflet that did not change.

    ``gallery_order`` and ``hidden`` name photographs by their ref or by the ref's own
    file name; the implementation resolves each against the profile's OWN gallery and
    refuses one it cannot place. An order must name every photograph the gallery holds:
    this is a re-ordering, and a photograph left off the list is not removed by it — it is
    refused, by name, so nothing disappears through an omission.

    ``add`` is the one way a photograph JOINS the gallery (2026-09-11): each ref must be
    an image the site already allocates — the file `asset.upload` just landed, by its ref
    or its file name — and is appended, shown, after the photographs already there. It is
    resolved against the SITE's images rather than the profile's gallery because it is
    not there yet; one the profile already holds is refused rather than doubled.
    """

    slug: str
    feature_ref: str | None = None
    gallery_order: tuple[str, ...] | None = None
    hidden: tuple[str, ...] | None = None
    summary: str | None = None
    bio: tuple[str, ...] | None = None
    #: The project's name as the site shows it (2026-09-10: "editing the title").
    title: str | None = None
    #: Photographs to append, by ref or file name, from the site's own images.
    add: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not str(self.slug or "").strip():
            raise SiteHostingError("a profile edit needs the profile's slug")
        if all(v is None for v in (self.feature_ref, self.gallery_order, self.hidden,
                                   self.summary, self.bio, self.title, self.add)):
            raise SiteHostingError(
                "a profile edit that changes nothing is not an edit: name a title, a "
                "feature image, an order, a hidden set, a summary, a description or a "
                "photograph to add")
        if self.gallery_order is not None:
            object.__setattr__(self, "gallery_order", tuple(
                t for t in (str(x or "").strip() for x in self.gallery_order) if t))
        if self.hidden is not None:
            object.__setattr__(self, "hidden", tuple(
                t for t in (str(x or "").strip() for x in self.hidden) if t))
        if self.bio is not None:
            object.__setattr__(self, "bio", tuple(
                t for t in (str(x or "").strip() for x in self.bio) if t))

    @property
    def changes(self) -> tuple[str, ...]:
        """Which of the five this edit carries, by name."""
        return tuple(name for name, value in (
            ("title", self.title),
            ("feature_ref", self.feature_ref), ("gallery_order", self.gallery_order),
            ("hidden", self.hidden), ("summary", self.summary), ("bio", self.bio),
        ) if value is not None)


@runtime_checkable
class SiteAuthoringPort(Protocol):
    """The authoring subset of the seam: read the site, publish a piece, take one down.

    A SECOND Protocol rather than a wider first one, because **a fill offering fewer
    functions is legal** — the port's own rule, stated where `email_provider` says a
    read-only relay is a valid filling. An adapter that publishes writing but performs no
    in-place edit is exactly that shape, and it is the first real one.

    So a caller checks the Protocol for what it NEEDS, not for everything the seam could
    ever do. Asking `isinstance(adapter, SiteHostingPort)` before publishing would refuse
    a perfectly good authoring adapter for lacking an image uploader, and the refusal
    would read as the adapter being broken.
    """

    def list_pages(self, *, site: str) -> tuple[EditablePage, ...]:
        ...

    def list_articles(self, *, site: str) -> tuple[PublishedArticle, ...]:
        """Authorized under :data:`OPERATION_PAGE_LIST` — see the module docstring."""
        ...

    def publish_article(self, *, site: str, draft: ArticleDraft,
                        fork_of: str = "") -> PublishedArticle:
        """``fork_of`` names a piece this one splits off from, for an edit that must not
        change its origin — a piece already sent to a list. Optional, and a fill that does
        not know the word behaves as it always did."""
        ...

    def read_analytics(self, *, site: str) -> tuple[dict[str, str], ...]:
        """One entry per period: visitors, sessions, views, bots. Reads, never writes."""
        ...

    def retire_article(self, *, site: str, slug: str) -> dict[str, Any]:
        ...


@runtime_checkable
class NewsletterSendingPort(Protocol):
    """The mailing half, as its OWN Protocol — for the reason the two above exist.

    A THIRD Protocol rather than a wider :class:`SiteAuthoringPort`, because widening that
    one would make every adapter that publishes but does not mail fail an ``isinstance``
    check it passes today, and the refusal would read as the adapter being broken rather
    than as it doing less. The port's rule is that a fill offering fewer functions is
    legal; an adapter that mails is an adapter offering one MORE, and the way to say that
    here is another Protocol, not a bigger one.

    So a caller about to send asks for exactly this, and a caller about to publish never
    has to care whether the adapter can mail.
    """

    def send_article(self, *, site: str, draft: ArticleDraft) -> SentNewsletter:
        """Authorized under :data:`OPERATION_ARTICLE_SEND` — and under nothing else."""
        ...

    def subscriber_count(self, *, site: str) -> int:
        """How many people a send would reach RIGHT NOW.

        Declared beside the send and authorized under the same operation, because it is
        the number the sender is entitled to see before choosing, and a surface that can
        offer the act must be able to state its size. Under the SEND rather than under
        `page.list`: this counts people who gave the site an address, which is not
        something a visitor already did in public.
        """
        ...

    def post_sent_newsletter(self, *, site: str, slug: str) -> PublishedArticle:
        """An issue already sent, put on the site as an article.

        HERE and not on :class:`SiteAuthoringPort` because it needs what this Protocol's
        adapters have and that one's may not: the private newsletter store, where an issue
        sent through an inbound-mail workflow is the only copy. Authorized under
        :data:`OPERATION_ARTICLE_PUBLISH` and not under the send — it puts words on a page
        and mails nobody, so an operator withholding the list does not withhold this.
        """
        ...


@runtime_checkable
class SiteHostingPort(SiteAuthoringPort, Protocol):
    """The WHOLE seam: everything above, plus the in-place editor's two writes.

    Satisfying this means an adapter can do all five operations. Nothing requires that —
    see :class:`SiteAuthoringPort`. Every method authorizes before it acts.
    """

    def list_pages(self, *, site: str) -> tuple[EditablePage, ...]:
        ...

    def replace_content(self, *, site: str, edit: ContentEdit) -> dict[str, Any]:
        ...

    def upload_asset(self, *, site: str, name: str, payload: bytes) -> dict[str, Any]:
        ...

    def export_project(self, *, site: str = "", export: ProjectExport) -> dict[str, Any]:
        """Write ``export``'s view beside the site's assets, land any picture the pool
        lacks, derive the profile from the view and rebuild — under
        :data:`OPERATION_PROJECT_EXPORT`."""
        ...


__all__ = [
    "OPERATION_ARTICLE_PUBLISH",
    "OPERATION_ARTICLE_RETIRE",
    "OPERATION_ARTICLE_SEND",
    "OPERATION_ASSET_SWAP",
    "OPERATION_ASSET_UPLOAD",
    "OPERATION_CONTENT_REPLACE",
    "OPERATION_PAGE_LIST",
    "OPERATION_PROFILE_EDIT",
    "SERVICE_LOCAL_TREE",
    "AmbiguousEdit",
    "ArticleDraft",
    "AssetSwap",
    "ContentEdit",
    "EditablePage",
    "NewsletterSendingPort",
    "ProfileEdit",
    "PublishedArticle",
    "SentNewsletter",
    "SiteAuthoringPort",
    "SiteHostingError",
    "SiteHostingPort",
    "SiteHostingUnavailable",
    "SiteProfile",
]
