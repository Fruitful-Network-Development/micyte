"""Which taxon a plant PHOTOGRAPH is of — resolved once, never guessed.

TASK-2026-09-12-001 A2. micyte.com holds 36 crop photographs named for their botany::

    <genus>_<species>[.<qualifier>].avif      solanum_lycopersicum.avif
                                              capsicum_annuum.sweet.avif
                                              cucurbita_spp.winter_squash.avif
                                              brassica_rapa.subsp_narinosa.avif

Until 2026-08-03 a deleted browser script matched them to taxa by slugifying a node's
botanical title and taking "the first match that is either an exact key or a longer key
starting with it", **on every page load**. That is a guess re-made by every reader, and
two readers could disagree about which plant a photograph shows. This module resolves the
question once so the answer can be stored as a datum reference.

## The ladder, in order, each step EXACT

A stem is slugified (lowercase, every run of non-alphanumerics to ``_``) and so is every
taxon title. Then, in order, stopping at the first step that yields exactly one node:

1. **the whole stem** — ``solanum_lycopersicum`` is a node's own title.
2. **the qualifier, under its base** — ``cucurbita_spp.winter_squash``: the qualifier
   names a cultivar-group node and the base says where to look, so only descendants of
   the base's node are considered. The base being unresolvable is not fatal here; a
   qualifier unique in the whole tree still resolves, and one that is not is reported.
3. **the base with its rank abbreviation dropped** — ``triticum_spp`` and
   ``x_triticosecale_sp`` name a genus whose node is titled ``Triticum``. ``_spp``,
   ``_sp``, ``_ssp`` and a leading ``x_`` (the hybrid mark) come off.
4. **the last token** — ``brassica_rapa.subsp_narinosa`` where the subspecies node is
   titled for the epithet alone.

A step that yields TWO nodes stops the ladder and is reported as ambiguous rather than
resolved by picking one: the later steps are broader, so falling through an ambiguity
would answer a looser question than the one that was already answered badly. A stem that
survives every step is reported as unmatched.

**No fuzzy matching, ever** — the rule the crop lexicon states
(`fnd_app/scripts/_market_alignment.py`): exact-then-longest-subset over sorted tokens,
and a pairing nobody can check is not a pairing. Here the equivalent is that every step is
an equality between two slugs, and everything else is a report.

Pure: the caller passes the stems and ``{node: title}``; nothing here reads a store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Rank abbreviations a filename carries that a taxon title does not.
_RANK_SUFFIXES: tuple[str, ...] = ("_spp", "_ssp", "_sp")
#: The hybrid mark, which leads a filename and not a title (``x_triticosecale_sp``).
_HYBRID_PREFIX = "x_"


def slug(value: Any) -> str:
    """A title or a filename stem, as the one comparable form: lowercase, every run of
    non-alphanumerics collapsed to ``_``, no leading or trailing separator."""
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _split(stem: str) -> tuple[str, str]:
    """``(base, qualifier)`` for a photograph stem — the qualifier is what follows the
    FIRST dot, which is the convention's own separator (``README.md`` beside the photos)."""
    base, _dot, qualifier = str(stem or "").partition(".")
    return base, qualifier


def _degraded(token: str) -> str:
    """A base with its rank abbreviation and hybrid mark removed, or ``""`` when it carries
    neither — so step 3 is only tried where it has something to do."""
    out = slug(token)
    changed = False
    if out.startswith(_HYBRID_PREFIX):
        out, changed = out[len(_HYBRID_PREFIX):], True
    for suffix in _RANK_SUFFIXES:
        if out.endswith(suffix):
            out, changed = out[: -len(suffix)], True
            break
    return out.strip("_") if changed else ""


@dataclass(frozen=True)
class Binding:
    """What one photograph resolved to, and by which step."""

    stem: str
    node: str = ""
    step: str = ""
    #: Every node the deciding step found. One when resolved, two or more when ambiguous.
    candidates: tuple[str, ...] = ()
    #: The nearest node the tree DOES carry for an unresolved stem, and what it is.
    #:
    #: Two unmatched photographs are different problems and the fix differs. A stem whose
    #: genus is absent names a plant the taxonomy does not carry at all; one whose species
    #: is present but whose cultivar group is not names something MORE SPECIFIC than the
    #: tree goes. Binding the second to its parent would say "a photograph of Capsicum
    #: annuum" about a photograph of sweet peppers, so it is reported instead — and the
    #: report says which of the two it is, because the first wants a taxon minted and the
    #: second wants a decision about precision.
    nearest: str = ""
    nearest_slug: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.node)

    @property
    def ambiguous(self) -> bool:
        return not self.node and len(self.candidates) > 1

    @property
    def why(self) -> str:
        """One sentence naming the fix, for an unresolved stem."""
        if self.resolved:
            return ""
        if self.ambiguous:
            return f"{len(self.candidates)} taxa carry this title; say which"
        if self.nearest:
            return (f"the tree carries {self.nearest_slug!r} ({self.nearest}) and nothing "
                    "more specific — mint the node or accept the broader one")
        return "no ancestor of this name is in the tree — the taxon would have to be minted"

    def to_dict(self) -> dict[str, Any]:
        return {"stem": self.stem, "node": self.node, "step": self.step,
                "candidates": list(self.candidates), "nearest": self.nearest,
                "nearest_slug": self.nearest_slug, "why": self.why}


@dataclass(frozen=True)
class BindingReport:
    """Every photograph's answer, and the two kinds of non-answer, kept apart.

    ``unmatched`` needs a photograph renamed or a taxon minted; ``ambiguous`` needs
    somebody to say which of two nodes it is. Both are decisions and neither is a
    mechanical fix, so both are reported and the write proceeds on the resolved set only —
    the fault asymmetry `micyte.core.sources` states.
    """

    bindings: tuple[Binding, ...] = ()

    @property
    def resolved(self) -> tuple[Binding, ...]:
        return tuple(b for b in self.bindings if b.resolved)

    @property
    def unmatched(self) -> tuple[Binding, ...]:
        return tuple(b for b in self.bindings if not b.resolved and not b.ambiguous)

    @property
    def ambiguous(self) -> tuple[Binding, ...]:
        return tuple(b for b in self.bindings if b.ambiguous)

    @property
    def by_stem(self) -> dict[str, str]:
        """``{stem: node}`` for the resolved ones — what a caller writes."""
        return {b.stem: b.node for b in self.resolved}

    def collisions(self) -> dict[str, tuple[str, ...]]:
        """``{node: the stems that resolved to it}`` where more than one did.

        Two photographs of one taxon is not an error — a species and its cultivar may
        both be shown — but it IS a fact the caller must see before writing, because a
        collection keyed by taxon would silently keep the last.
        """
        seen: dict[str, list[str]] = {}
        for binding in self.resolved:
            seen.setdefault(binding.node, []).append(binding.stem)
        return {node: tuple(stems) for node, stems in seen.items() if len(stems) > 1}

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": [b.to_dict() for b in self.resolved],
            "unmatched": {b.stem: b.why for b in self.unmatched},
            "ambiguous": {b.stem: list(b.candidates) for b in self.ambiguous},
            "collisions": {node: list(stems) for node, stems in self.collisions().items()},
            "counts": {"stems": len(self.bindings), "resolved": len(self.resolved),
                       "unmatched": len(self.unmatched), "ambiguous": len(self.ambiguous)},
        }


def _index(titles: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """``{slugified title: the nodes carrying it}`` — many nodes may share a common name."""
    out: dict[str, list[str]] = {}
    for node, title in titles.items():
        key = slug(title)
        if key:
            out.setdefault(key, []).append(str(node))
    return {key: tuple(nodes) for key, nodes in out.items()}


def _under(nodes: tuple[str, ...], base_nodes: tuple[str, ...]) -> tuple[str, ...]:
    """Those of ``nodes`` that are ``base_nodes`` or beneath one — a SAMRAS address is its
    own path, so descent is a prefix test and nothing needs to be declared about it."""
    if not base_nodes:
        return nodes
    return tuple(n for n in nodes
                 if any(n == b or n.startswith(f"{b}-") for b in base_nodes))


def bind(stems: Any, titles: dict[str, str]) -> BindingReport:
    """Resolve each photograph stem to one taxon node. See the module docstring's ladder."""
    index = _index(titles)
    bindings: list[Binding] = []
    for raw in stems:
        stem = str(raw or "")
        base, qualifier = _split(stem)
        steps: list[tuple[str, tuple[str, ...]]] = []

        whole = index.get(slug(stem), ())
        steps.append(("whole stem", whole))

        if qualifier:
            base_nodes = index.get(slug(base), ()) or index.get(_degraded(base), ())
            steps.append(("qualifier under its base",
                          _under(index.get(slug(qualifier), ()), base_nodes)))

        degraded = _degraded(base)
        if degraded:
            steps.append(("base without its rank abbreviation", index.get(degraded, ())))

        last = slug(stem).rsplit("_", 1)[-1]
        if last and last != slug(stem):
            steps.append(("last token", index.get(last, ())))

        chosen = Binding(stem=stem)
        for name, found in steps:
            if not found:
                continue
            chosen = Binding(stem=stem, node=found[0] if len(found) == 1 else "",
                             step=name, candidates=tuple(found))
            break
        if not chosen.resolved and not chosen.ambiguous:
            # What the tree DOES carry on the way to this name: the longest leading run of
            # the base's tokens that is one node's title. `brassica_rapa.var_rapa` finds
            # `brassica_rapa`; `achillea_millefolium` finds nothing, and those are
            # different problems.
            tokens = slug(base).split("_")
            for cut in range(len(tokens), 0, -1):
                key = "_".join(tokens[:cut])
                found = index.get(key, ())
                if len(found) == 1:
                    chosen = Binding(stem=stem, nearest=found[0], nearest_slug=key)
                    break
        bindings.append(chosen)
    return BindingReport(bindings=tuple(bindings))


__all__ = ["Binding", "BindingReport", "bind", "slug"]
