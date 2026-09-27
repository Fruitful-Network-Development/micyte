# 42 — The Glyph Library

> Status: as-built
>
> [← Overview](00-overview-and-glossary.md)

## A drawing IS its rows

A glyph document is not a description of a picture, and not a pointer to one. Its rows
decode to **one `d` attribute** and nothing else is consulted.

That is the third instance of the move [`41-archetypes-and-viewscopes.md`](41-archetypes-and-viewscopes.md)
describes: a kind stopped being Python, a layout stopped being JavaScript, and here a
*picture* stops being an asset. Codec:
[`micyte/core/datum_ops/glyph.py`](../../micyte/core/datum_ops/glyph.py).

## The grammar, and why it is restricted

One `M` per path, then `A` commands and nothing else. **No `C`, no `Q`, no `Z`, no second
`M`.**

Narrow on purpose: every command the grammar admits has to be expressible as datum rows of
a fixed arity. A grammar that quietly accepts what it cannot re-emit is not a grammar —
it is a parser with a lossy branch, and the lossy branch is discovered later by a drawing
that came back different from the one that went in.

Three things are **fixed rather than stored**, because the operator fixed them:

| fixed | value |
|---|---|
| arc x-axis rotation | always `0` |
| colour | always the host's `currentColor` |
| path closure | never closed |

The rule behind all three: *a field nothing writes is a field six readers will disagree
about.* Storing a rotation nobody varies invites one reader to honour it and another to
ignore it.

## `currentColor` is the whole theming story

An externally-referenced `<use>` is themed by `color` and by nothing else — no
`fill`, no `stroke`, no CSS from the host document reaches inside it. That is why the
colour is fixed: the glyph inherits, and the host decides. And an external `<use>`
reference needs the `icon-` prefix to resolve at all.

## Where glyphs live

- [`fnd_app/scripts/bootstrap_glyph_sandbox.py`](../../fnd_app/scripts/bootstrap_glyph_sandbox.py) — creates the sandbox
- [`fnd_app/scripts/seed_glyph_library.py`](../../fnd_app/scripts/seed_glyph_library.py) — fills it

The library has two branches, **icons** and **documents**, and the split is not
decorative: an icon is drawn at rail scale and a document mark is drawn at 512×512, so a
drawing authored for one reads as a smudge or a blueprint in the other.

## Every sandbox holds the eleven

Since 2026-09-08 a local domain is provisioned with the canonical drawings COPIED in under
its `glyphs` branch (`1-1-1-1` … `1-1-1-11`: circle, disc, dot, ring, square, document,
folder, anchor mark, log, link, code brackets — `CANONICAL_GLYPHS`), and every node wears
one. Copied, not referenced: a glyph's rows cite only its own anchor's abstractions, which
every anchor carries by logical name, so the sandbox keeps drawing if FND is unreachable.
The slot numbering is the same in every sandbox, so a drawing that arrives later fills the
slot that was always its own. `circle` is the default an ordinary node wears; the
structural nodes wear fixed ones (`STRUCTURAL_GLYPHS`); a glyph slot wears itself.

## Authoring a glyph

Draw within a 512×512 box, in one `M` plus arcs. If the shape needs a curve the grammar
does not have, the answer is to re-express it in arcs — not to widen the grammar, because
widening it re-opens the lossy-branch problem for every glyph already stored.

## See also

- [`41-archetypes-and-viewscopes.md`](41-archetypes-and-viewscopes.md) — the same move, twice more
- [`43-local-domain-log.md`](43-local-domain-log.md) — how a node points at a document
