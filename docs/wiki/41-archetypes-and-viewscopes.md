# 41 — Archetypes & Viewscopes

> Status: as-built
>
> [← Overview](00-overview-and-glossary.md)

## The one idea

Three things stopped being code and became **data** in this system, and they are the
same move made three times:

| what it was | what it is now | where |
|---|---|---|
| a document's KIND, in Python | an archetype document | [`micyte/core/archetypes/__init__.py`](../../micyte/core/archetypes/__init__.py) |
| a document's LAYOUT, in JavaScript | a viewscope document | [`micyte/tools/_viewscope.py`](../../micyte/tools/_viewscope.py) |
| a PICTURE, as an asset file | a glyph document | see [`42-glyph-library.md`](42-glyph-library.md) |

Read that column downwards and it is one sentence: **the thing that decides how data is
treated is itself data, held in the same store, addressed the same way.**

## An archetype is a blank instance, not a description of one

This is the distinction to carry away, because it is what makes the registry
self-checking. An archetype does not *describe* the shape a document should have — it
*is* a document of that shape, with the values left blank. So "does this document match
its archetype?" is answered by the same fold that built the archetype, not by a
validator written separately and free to disagree with it.

`build_registry` reads only documents whose metadata says `role == "archetype"`, folds
them with [`archetype_shape`](../../micyte/core/datum_ops/archetype_shape.py), and never
consults the registry it is building. That is the bootstrap dependency, and it is bounded
on purpose: the registry is canonical data *about* canonical data, and it must not need
itself to load.

Question 4 of [`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md)
asked where the registry should be sourced — in-code constant, MOS document, or per-tenant
config. This is that question answered: the MOS document, self-hosting.

## A viewscope says how a document is DRAWN

The workbench had two view modes, both spreadsheets — `interpreted` and `raw`. A viewscope
is the third, and it is not a third spreadsheet: it shows a document **as the thing it
is**. A boundary as geometry, a directory as lines, a jurisdiction as a name beside its
boundary. Which primitives draw it is a fact the archetype carries.

**The shape selects the render.** Nothing about the surface decides what a document looks
like; the document's own declaration does.

### Cost is the reason it is built this way

Worth stating plainly because it is measured, not asserted:

- `read_authoritative_datum_documents` parses one **138 MB** blob holding all 544
  documents (~350 MB warm) — which is why a document-level write costs this portal
  ~690 MB.
- A viewscope reads the subject document from `datum_document_semantics` — **6 KB** for
  the median document — plus the archetype library in one per-sandbox read: **34
  documents in 0.004 s at 22 MB**.

Nothing in the viewscope path touches the catalog. The four biggest documents in the
store (42 MB, 30 MB, 27 MB, 12 MB) are refused rather than drawn.

## Editing through a viewscope, and why most slots refuse

Only ASCII-radix (`2-1-1`) slots are writable. `refusal_for(primitive, address, radices)`
answers in a fixed order, and the order matters because each step is a *different*
question:

1. no such primitive
2. no such address
3. no such radix
4. the radix is not ASCII
5. writable

A slot backed by a fiat radix (`2-2-1`) is not free text — it is money — so it refuses
with that reason rather than a generic "read only". A refusal that names which of the five
it hit is the difference between a bug report and a shrug.

## See also

- [`40-tools-and-lenses-asbuilt.md`](40-tools-and-lenses-asbuilt.md) — how tools bind (marked `stale`; read it for the contract, not the census)
- [`42-glyph-library.md`](42-glyph-library.md) — the same move applied to drawings
- [`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md) — the open question this answers
