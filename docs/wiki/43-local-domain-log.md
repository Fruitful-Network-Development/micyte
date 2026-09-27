# 43 — The Local Domain

> Status: as-built (base structure 2026-09-08; the log 2026-08-19)
>
> [← Overview](00-overview-and-glossary.md)

## Every local domain has the same base structure

A sandbox's local domain (`lcl_domain`) is its own id space and the log of what each id
names. Since 2026-09-08 every one starts with the same tree, found **by label** at every
level — the ordinals are only where the seed puts it, because `insert_node` can re-key
any address.

```
1        local_domain
1-1      meta
1-1-1    glyphs        1-1-1-n   a drawing (the eleven canonical ones, `circle` first)
1-1-2    documents     1-1-2-n   a slot: a datum document, NAMED for the slot
           1-1-2-1  anchor       reserved
           1-1-2-2  local_domain reserved
1-1-3    sources       1-1-3-n   a pin: <msn>.<name> and a content hash
1-1-4    artifacts     1-1-4-k   a KIND: image · record · video · memo
                       1-1-4-k-n an artifact slot, under its kind
1-2      classes       1-2-1 archetypes · 1-2-2 datum_types · 1-2-3 events
1-3      objects       the operator's own tree — free-form beneath here
```

**One root.** The operator's tree is `objects`' children. A canonical tree cannot take a
second top-level node; "add a top-level branch" files it under `objects`.

Codec: [`micyte/core/datum_ops/local_domain.py`](../../micyte/core/datum_ops/local_domain.py)
(`ROOT_LABEL`, `META_LABEL`, the branch labels, `ARTIFACT_KINDS`, `CLASS_KINDS`,
`CANONICAL_GLYPHS`, `STRUCTURAL_GLYPHS`). Seed:
[`micyte/core/instance_baseline.py`](../../micyte/core/instance_baseline.py)
`seeded_local_domain_rows`. Provisioner:
[`fnd_app/instances/_shared/runtime/local_domain_provision_runtime.py`](../../fnd_app/instances/_shared/runtime/local_domain_provision_runtime.py)
— the one resolver every creator of a sandbox calls.

## The address IS the arity, and the floor is `4-3`

A datum address is `<layer>-<value_group>-<iteration>` and **value_group is the tuple
count**. So a row's shape is declared by where it lives:

| address | row | meaning |
|---|---|---|
| `4-3-N` | `[addr, lcl_id, <node>, title, <bits>, lcl_id, <glyph>]` | a node, wearing a glyph — **the floor** |
| `4-4-N` | `… , lcl_id, <glyph>, lcl_id, <slot>]` | a node that also **denotes** one thing |
| `4-4-N` | `… , lcl_id, <glyph>, mss_source_binary, <hash>]` | a **source** pin |
| `4-2-N` | `[addr, lcl_id, <node>, title, <bits>]` | a bare node — read, never written where a glyph exists |

Every node wears a glyph; a glyph slot wears itself; the structural nodes wear fixed ones.
The fourth cell of a `4-4` row is the ONE thing the node denotes — a document slot, an
artifact slot or a source pin — and **the branch that slot sits under says which**. There
is no fifth family and no second archetype: `local_domain_log` is `L4:lcl_id,title,lcl_id+`
(the run covers wearing-only and wearing-and-denoting) and `local_domain_source` is
`L4:lcl_id,title,lcl_id,mss_source_binary`.

The writers hold the floor: `LclBuilder._add_row` defaults the glyph to the sandbox's
`circle`, `set_node_icon("")` refuses, a created document's slot wears `document`, and an
inserted group wears the default. A tree with **no** glyph branch — the pre-2026-09-08
shape — keeps writing `4-2`, because a default glyph that does not exist would be a
dangling reference written into every node at once.

## The anchor denotes exactly the tree

The anchor's `lcl-SAMRAS` magnitude is the tree's population; the surface draws what the
**magnitude** denotes and labels from the document. A copied anchor keeps the source
sandbox's magnitude, so the seed recompiles it (`seeded_anchor_rows`) and every verb
recompiles it after writing. A node the magnitude denotes and the log does not define
draws as `(undefined)` — that is a stale anchor, not a missing title, and
`check_denotation` says so.

## One definition row per node

A node has **one** definition row. Attaching a document MOVES it from `4-3` to `4-4`;
detaching moves it back. `NameIndex` resolves by first row in document order, so a second
row makes a node's label order-dependent and its kind ambiguous.

## Two denotations, or none

A node that denotes a document names it, and the document is reachable at that address.
Half of that pair is worse than neither — a pointer that resolves to nothing looks exactly
like a feature that has not been built yet. A source is the same pair across a boundary:
the title names the document, the hash says which version, and the resolver reports
`fresh` / `stale` / `missing` rather than guessing.

## Why the log and the tree are the same object

A sandbox view **is** its domain, opened. The tree a browser draws is the log read, so a
node cannot appear in one and be absent from the other.

## The convention is a document

Since 2026-09-11 (TASK-2026-09-11-001 P4) the base structure above is not only what the
code seeds: it is what the archetype library's own `lcl_domain` STATES, and the seed reads
it from there. `micyte/core/datum_ops/local_domain_convention.py` reads a tree into a
`Convention` — the branch labels, the glyph each structural role wears, the canonical
glyph titles, the artifact and class kinds, and the class vocabularies the convention
seeds (`project_roles`, `project_facts` — see [44](44-project-documents.md)). The code's
constants are the BOOTSTRAP for a store with no library and a test holds the two in
agreement (`disagreements` is empty), so an edit made in the library that the code
cannot honour is a red test, never a drift.

**Edited where every tree is edited.** The `convention` surface opens the library's tree
in the Domain editor — `set_node_icon`, `rename_node`, `move_node`, `insert_node`, posted
with the library's sandbox and gated as everywhere — and draws it with the viewscope
beside. The viewscope is not a second editor; it is what draws the document as the tree
it is, bound by the archetype (`local_domain_log`), never by a tool id.

**Pinned, and pinged.** Every tree pins `<msn>.archetype_lcl_domain` in its sources
branch (`AUTHORITY_SOURCES`), so the sources resolver's own verdict applies: `fresh` when
the pin is the library tree's current version, `stale` when the library moved, `unpinned`
when the tree predates the pin. `convention_runtime.convention_status` asks every tree
cheaply (one semantics read each), healthz carries `convention: fresh | stale(n)`, the
surface lists each tree with the one verb, and `fnd_app/scripts/apply_convention.py`
runs it over the store. `apply_convention` mints the kinds and vocabulary words a tree
lacks, re-wears the structural glyphs the convention names, and moves the pin — in one
tree write, removing and relabelling nothing.

## The legacy shape

Trees minted between 2026-08-20 and 2026-09-08 carried a root labelled `documents` with
`icons` and `documents` beneath it and the operator's tree at root `2`. All 25 live trees
were moved to the base structure on 2026-09-09. `read_log` reads the base structure and
nothing else: to it a tree without a `local_domain` root has no log — no branches, no
reserved pair, no glyph — and every verb refuses by name rather than guessing. The old
shape is read by exactly one program, `migrate_local_domain_base._read_legacy_log`, the
one that needs it in order to leave it.

## See also

- [`42-glyph-library.md`](42-glyph-library.md) — the eleven drawings every sandbox holds
- [`60-canonical-datum-and-hyphae-flags.md`](60-canonical-datum-and-hyphae-flags.md) — datum addressing and the rudi frames
- [`41-archetypes-and-viewscopes.md`](41-archetypes-and-viewscopes.md) — what decides how a denoted document is DRAWN
