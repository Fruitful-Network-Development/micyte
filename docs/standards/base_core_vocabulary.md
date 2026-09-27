# The base core's vocabulary

One page, one definition each, and the module that OWNS the term. Written on 2026-08-20 at
the operator's request — "so that I can more cleanly define terms and avoid drift" — because
a term with two owners is a term two pieces of code will one day disagree about.

**How to read the Owner column.** It names the module that DECIDES the term, not every
module that uses it. A second module deciding the same thing is the defect this page exists
to make visible: when you find one, delete it and import from the owner.

---

## The furniture

| Term | Owner | What it is |
|---|---|---|
| **instance** | `micyte/core/instances.py` | A set of sandboxes sharing one msn. Every instance keeps its own core sandbox, and three of them call it `system` — so a sandbox NAME is not an address; the `(msn, sandbox)` pair is. |
| **sandbox** | `micyte/core/document_naming` | A named space of datum documents inside one instance. It has an anchor and a local domain and nothing else is required. |
| **anchor** | `micyte/core/document_naming.ANCHOR_DOCUMENT_NAMES` | The document every other document in the sandbox resolves against. Called `anchor` or `anthology`; ask about the pair, never one literal. Copied from an existing one, never invented. |
| **local domain (log)** | `micyte/core/document_naming.LOCAL_DOMAIN_DOCUMENT` | The sandbox's lcl id-space, and the log of which document each id names. Canonical name `lcl_domain` since 2026-08-20; `lcl` is the legacy spelling and is read through `LOCAL_DOMAIN_DOCUMENT_NAMES` until the store holds none. |
| **datum document** | `micyte/core/datum_documents.py` | Rows of datums under one canonical id, `lv.<msn>.<sandbox>.<name>.<version_hash>`. |
| **archetype** | `micyte/core/archetypes.py` | A blank INSTANCE of a shape. A document's archetype is FOLDED from its rows, never declared by it. |
| **class** | `micyte/core/datum_ops/archetype_class.py` | What several archetypes have in common, and what draws them when none of them draws itself. |
| **viewscope** | `micyte/tools/_viewscope.py` | The archetype-driven renderer for ONE document. A question that spans documents has no viewscope by construction. |

## The local domain log's own terms

| Term | Owner | What it is |
|---|---|---|
| **node** | `micyte/core/datum_ops/local_domain.py` | One address in the sandbox's lcl tree, defined by exactly ONE row. Two definition rows make a node's label order-dependent. |
| **value group** | `micyte/core/mss/document_codec` | The tuple count. It IS the middle number of a datum address, which is why a 2-tuple lcl row lives at `4-2-N` and a 3-tuple one at `4-3-N`. Nothing invented this convention; it is where the rows have to live. |
| **documents branch** | `local_domain.DOCUMENT_ROOT_LABEL` | The reserved root the whole id-space hangs from. Found by its LABEL, never by the address `1` — `insert_node` can re-key any address, and five live trees carry it at `2`. |
| **icon branch / document branch** | `local_domain.ICON_BRANCH_LABEL` / `DOCUMENT_BRANCH_LABEL` | The two children of the documents branch, found by label one level down. The split is not filing tidiness: an icon reference and a document pointer are the same `lcl_id` marker naming a node, so only the BRANCH tells them apart — which is what lets one row family carry either. |
| **slot** | `local_domain.LocalDomainLog.slots` | A child of the DOCUMENT branch. Its LABEL is the document's title and its ADDRESS is the document's filename. |
| **glyph** | `micyte/core/datum_ops/glyph.py` | A drawing whose ROWS are the drawing: one `M` per path, `A` commands only, on a 512x512 canvas. A datum document like any other, filed on the icon branch of whatever sandbox wears it. |
| **icon** | `local_domain.LocalDomainLog.icon_of` | A node's glyph, named by its slot on the icon branch. Data, never a render-time default: a node either wears one or it does not, and the difference is a cell. |
| **reserved slot** | `local_domain.ANCHOR_SLOT_ORDINAL` / `LOG_SLOT_ORDINAL` | The first two slots on the DOCUMENT branch name the anchor and the log. Both keep their reserved FILENAMES, because every reader finds them by name and a document that could only be found through the log cannot BE the log. Real rows, not a promise: node ordinals must be contiguous from 1. |
| **filed / unfiled** | `local_domain.filed_documents` | A document is FILED when a slot names it. Unfiled is the honest state for most of the corpus — registrar's documents are named for the msn nodes they profile, the archetype library's for the archetype they blank-instance, and in both the name IS the denotation. |
| **denotes** | `local_domain.trailing_refs` | A node DENOTES a document when its definition row carries a trailing tuple naming a slot on the DOCUMENT branch. Exactly one document per node, and a node with children denotes none (the leaf rule). A trailing tuple naming the ICON branch is a glyph instead, and a row may carry both — icon first. |
| **writing** | `micyte/tools/_domain_reading.py` | The document a node denotes, read as text. |
| **answer** | `local_domain.slot_title` | A slot titled `<node> <option>`. An answer is a DOCUMENT and never a child node, because a node holding a writing takes no children. |
| **reference** | `_domain_reading.action_reference` | A writing whose WHOLE text is a node address. "3-1, because Brock said so" is prose with an address at the top. |

## The Compendium

| Term | Owner | What it is |
|---|---|---|
| **level** | `portal_workbench_ui_runtime._attach_compendium_payload` | What the address names: 0 the instance's shelf, 1 a sandbox or an instrument, 2 an open document. The canonical query addresses the level the REQUEST named — never the level a selection wandered to. |
| **sandbox view** | same, `_VIEW_DOMAIN` / `_VIEW_LIST` | Level 1 for a sandbox IS its local domain log opened: `domain` is the node graph, `list` is the log read as a table. There is no `gallery`; it listed the same documents a third time. |
| **shelf** | same, `_sandbox_shelf` | Every document a sandbox holds, each with its slot, its title and whether the log knows about it. |
| **instrument** | `micyte/tools/_instruments.py` | An artifact that interfaces with one datum KIND across every sandbox of an instance — `calendar`, `rolodex`, `profile_interface`. It holds nothing, has no anchor, and cannot be browsed into. Read-only, because each spans documents another surface owns. Listed on the GADGETS gallery (2026-08-21), not the Compendium shelf; `?instrument=<id>` on the Compendium root is still its face's address. |
| **activity bar** | `portal_shell_runtime._activity_items` / `_activity_footer` | Exactly the portal's five axes (2026-08-21): Network, Compendium, Gadgets, Utilities hugging the top, Profile at the actual bottom — a bottom BAR on a phone, ordered Utilities · Gadgets · Network · Compendium · Profile. A rail item is a page, never a launcher. |
| **gadgets** | `gadgets_surface.build_gadgets_payload` | The launcher page (`/portal/gadgets`): installed apps (the per-msn install pin) and the instruments, two groups behind one thin floating divider. Every entry is an address on the Compendium root. |
| **profile interface** | `profile_interface_runtime` | The identity surface (`/portal/profile`, and the gallery's instrument): the instance's registrar card + `msn_profile`, its alias/channel cards (an alias document is `system/<channel>-<host_msn>`), and the session — the instance switcher and sign-out. A channel card opens that channel's session IN the page; the Registrar card opens the Network page (the 'special core' channel). |
| **grantor** | `micyte/channels/grantor.py` | The CLOSED channel FND serves its clients through: an `accounts` roster of client grantees and one `grantee-<msn>` service document each (service, state) — email locked-enabled, the copyable port-enabling service key, and the admin Tolling tab over the derived invoices. Grayed on its own host's profile: served per alias, and the host has no alias of itself. |

## The glyph library

| Term | Owner | What it is |
|---|---|---|
| **restricted grammar** | `micyte/core/datum_ops/glyph.py` | One `M` per path and `A` commands only. Narrow on purpose: every command it admits has to be expressible as rows of a fixed arity, and a grammar that quietly accepts what it cannot re-emit is a parser with a lossy branch. Colour, stroke width, closure and the x-axis rotation are FIXED, not stored. |
| **grid point** | `field_registry` `GLYPH`/`ARCHETYPE` `grid_point` | A position on the 512x512 canvas: 262,144 of them, **18 bits**, `x` in the high nine. Its babelette is `4-1-1` and can be nowhere else — a babelette's LAYER is its chain's depth, and `((((siu;512:);512:);1:);0)` is four deep. The only field in the registry outside `3-1`. |
| **length** | same, `length` | A radius or extent, **9 bits**, stored as `value - 1` over 1..512. Without the offset the rectangle's first arc has a radius of zero, and SVG draws that as a straight line. |
| **`glyph_canvas`** | `viewscope.CONTAINERS` | The container that draws a document rather than its fields. It declares no slots because a glyph has none. Not a primitive: `symbol` renders a FILENAME, and a glyph has no file. |
| **size ladder** | `v2_portal_viewscope.js` | The same glyph at 16, 24 and 48 beside the canvas. The only question anyone has about an icon is whether it still reads small, and a 512px preview cannot answer it. |

## Sources

| Term | Owner | What it is |
|---|---|---|
| **source (pin)** | `micyte/core/sources.py` | A row in a sandbox's `sources` manifest naming another document and pinning its content hash. A consumer resolves a document by the name it declared, or it does not get the document. |
| **origin** | `sources.origin_of` | Where a pin comes from: `own` (this sandbox published it), `internal` (another sandbox of this instance), `external` (outside the instance). Derived — a pin names its sandbox and the instance knows its own. |
| **delivered** | `sources.is_delivered` | A pin that ARRIVED as a contract payload rather than one this instance reached for. A delivered pin the resolver calls `stale` has an update waiting. |
| **fresh / stale / missing / unverifiable** | `sources.SOURCE_FAULTS` | Stale is a FAULT with a mechanical fix (re-pin it). Missing and unverifiable need a decision about the data, so they are reported and not gated on. |

## Ports

| Term | Owner | What it is |
|---|---|---|
| **port type** | `micyte/ports/port_catalog` | An inward-facing contract — `email_provider`, `ai_provider` — and the operations it declares. |
| **extension** | `micyte/ports/tool_package.PortFill` | A marketplace package that FILLS one or more port types. |
| **binding** | `micyte/ports/port_binding` | This instance selected that extension for that port, for these sandboxes. Describing a connection. |
| **grant** | `micyte/ports/datum_write_policy`, `external_call_policy` | Whether it MAY. Hand-written in config, never derived, and never writable from a surface — describing and permitting are two acts, reviewed separately. |
| **sandbox settings** | `sandbox_settings_surfaces.py` | Which ports may act on ONE sandbox. The same rows Utilities computes, re-presented; Utilities keeps only presence and connection. |

---

## Terms deliberately retired

Naming what is GONE is half of avoiding drift — a term with no referent is a term somebody
will use again.

| Retired | When | What replaced it |
|---|---|---|
| `lcl` (the document name) | 2026-08-20 | `lcl_domain`. Read through `LOCAL_DOMAIN_DOCUMENT_NAMES` until the store holds none. |
| `note_<lcl_id>` / `note_<node>_<option>` | 2026-08-20 | A slot, and the title cell. Zero documents on the corpus carried the prefix after the migration. |
| `note_manager` (the Notes shelf) | 2026-08-20 | The Domain surface, where a writing is shown ON the node it is about. |
| `add_note` / `attach_note` / `delete_note` | 2026-08-20 | `create_document`, `attach_document`, and deleting the slot. |
| the level-1 `gallery` face | 2026-08-20 | The sandbox's own local domain log, opened. |
| `AppSandbox.local_domain_log` | 2026-08-20 | Nothing — the documents branch is universal, and a flag for something universal has a false branch nothing tests. |
| `home_config`, `agro_calendar` | 2026-08-16 | The document layer; the network cadence calendar was retired outright. |
| `POINTER_FAMILY` (the name) | 2026-08-20 | `REF_FAMILY`, and `DEFINITION_FAMILIES` for readers that mean "is this a definition row at all". Six of them named the two families by hand and would have gone silently blind to the third. |
| `local_domain.pointer_of` as the READ | 2026-08-20 | `trailing_refs` plus classification by branch. `pointer_of` survives as the FIRST trailing reference and is unclassified — on a subdivided tree that is the icon, so a caller meaning "the document" asks the log. |
| `?document=<short name>` (the Open link) | 2026-08-20 | `?document=<canonical id>`. The workbench resolves ids; a name matched none and fell back to the sandbox's preferred document, so every Open on every tree opened the ANCHOR while looking like it had worked. |
| `parent == log.meta_root` as "is a slot" | 2026-08-20 | `log.is_slot_node` / `is_icon_node` / `is_document_node`. Nine readers spelled it by hand and every one of them went false for every slot the moment the branch subdivided. |
| `vector-effect: non-scaling-stroke` on a glyph | 2026-08-20 | A stroke in USER units. The non-scaling form holds the width at constant SCREEN size, so an 8px line on a 16px icon is half the icon. |

## Named, and NOT retired

Retiring a term needs somewhere for its referent to go. These have nowhere yet, and saying
so is what keeps the list above honest.

| Still here | Why |
|---|---|
| the leaflet pool + `build_portal_icon_sprite.py` | 527 files at 24x24 using `M/H/V/C`. The glyph library holds ten shapes drawn in one-M-all-A at 512; re-expressing the rest is a drawing job, not a script, and a lossy auto-conversion would fill the canonical library with shapes nobody chose. The sprite retires one id at a time, as a real glyph stands behind it. |
| `icon_ref` as a leaflet stem | The taxonomy's 100+ nodes carry one. Same reason. |
| `note` (the document KIND) | A writing is still a `text_note` archetype. The NAME convention retired; the kind did not. |
