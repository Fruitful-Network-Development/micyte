# MSN Contact Card & Profile — canonical field standard (v1)

**Status:** design-spec (v1). Defines the standardized datum-document shape for an
entity's public **msn contact card** and its **msn profile**, and the canonical
logical-field vocabulary every MiCyte instance should speak. This is the network
standard a registry publishes and a browser (e.g. a public directory site) reads.

## Concepts

- **msn contact card** — the small, public-by-consent datum document a portal
  advertises for an entity: enough to resolve the entity's address and reach it, and
  no more. It is a *single filament datum* — one row whose head carries typed
  `(field → value)` cells.
- **msn profile** — a datum document that **extends** the contact card with the rest
  of an entity's standardized public detail. Card ⊂ profile.
- **entity kind** — at the network level there are exactly four kinds:
  `legal`, `natural`, `administrative`, `informal`. (Sub-types of legal entities, and
  the *farm* extension, are out of scope for v1; they only affect how downstream tools
  and instance packages preload information.)

This mirrors the existing base→extension pattern in the codebase: the base datum
visualizer (`profile_card`) is the hardened contract that richer profiles
(`farm_profile`) build on. The card/profile split is that same move, standardized.

## The datum type stack (recap)

A datum's *type* is declared by referencing a lower-abstraction datum. The stack:

```
rudi      0-0-*   primitive alphabet (time/space/nominal/mass/json units)
bacillete 1-1-*   a radix (base-N)
lcl       1-2-*   local classification nodes
baciloid  2-1-*   a concrete type = base-N × M digits ("just short of an instance")
space     2-0-*   a HOPS/SAMRAS coordinate space (refs-only)
babelette 3-1-*   a NAMED field binding an abstraction to a marker (rf.3-1-N)
instance  4-*/7-* an actual value; a filament = one row of (rf.<babelette>, value) cells
```

A contact card is thus a `4-*`/`7-*` filament row whose cells reference the babelettes
below. Each babelette is a `{datum_address, raw:[[self, downward_ref, "0"], [label]]}`
row on an anchor.

## Canonical field vocabulary (v1)

One **logical field name** per concept, with its canonical backing type. Instances and
anchors may (today) place these at different physical `3-1-N` addresses; code MUST
resolve fields by logical name through the field registry, never by a hardcoded
`rf.3-1-N` literal (see `field_registry`).

| Logical field | Backing abstraction | Notes |
|---|---|---|
| `msn_id` | SAMRAS-space-msn | the entity's own network address (the card's self key) |
| `txa_id` | SAMRAS-space-txa | taxonomy address (where applicable) |
| `lcl_id` | SAMRAS-space-lcl | local-classification node |
| `ruiqi_id` | SAMRAS-space-ruiqi | registrar name-binary |
| `coordinate` | HOPS-space-spacial | lat/lng ring |
| `utc` | HOPS-space-chronological | canonical spelling is *chronological* |
| `name` | niu-baciloid-256-32 | display name (≤32 ASCII) |
| `title` | niu-baciloid-256-64 | legal/long title (≤64 ASCII) — **canonical width 64** |
| `common_name` | niu-baciloid-256-64 | vernacular name |
| `dns` / `website` | niu-baciloid-256-255 | reachable domain — **canonical base-256 × 255** |
| `email` | niu-baciloid-256-320 | contact email |
| `ipv4` | niu-baciloid-8-4 | |
| `ipv6` | niu-baciloid-8-6 | |
| `visual` | ref → 0-0-11 (json-file-unit) | logo/image is a **reference** (URL or content hash), never raw bytes in MOS |
| `icon_ref` | niu-baciloid-256-64 | taxonomy/clade icon reference |
| `jurisdiction_type` | niu-baciloid-256-64 | administrative entities |
| `region_polygon_ref` | SAMRAS-space-msn | boundary node reference |
| `dns_present` | bit (see below) | **new** — is a `micyte-<msn_id>.bin` served at the site root? |
| `entity_kind` | = `lcl_id` → depth-3 network kind | **not a separate field** — see below |
| `active` | bit (see below) | **new** — relational, cached |

### `entity_kind` — the card's `lcl_id`, collapsed to a network kind

`entity_kind` is **not a separate field**: it is the card's existing **`lcl_id`**
(`rf.3-1-13`), collapsed to one of the four network kinds. The `lcl` document defines the
entity-class subtree under `1-1-*`; the four network kinds are its **depth-3** nodes:

```
entity_kind: legal (1-1-1) | informal (1-1-2) | administrative (1-1-3) | natural (1-1-4)
```

A legal entity's stored `lcl_id` may be a **subtype** (`1-1-1-1` llc, `1-1-1-3` nonprofit,
`1-1-1-2` corporation, …); "types of legal entities" are out of scope for the network v1, so
the card's kind is the subtype's **depth-3 ancestor**
(the registrar-card backfill's `_network_kind` rule — there is no literal 'type-node' marker in the
`lcl` doc; depth is the discriminator). Only `legal_entity` rows carry their own `rf.3-1-13`;
`natural`/`administrative` rows carry none and are the fixed kinds `1-1-4`/`1-1-3` by
construction. Resolving a card's kind is therefore: read its `lcl_id`, take its depth-3
network node, label it. The card's `lcl_id` is thus the single source of the classification —
the feed reads it from the `registry` card doc (`publish_micyte_registry._registry_kinds`),
rather than re-deriving it from a who-drives-it colour bucket. (The map's glyph *colour*
class is a separate presentation concern.)

### `active` and `dns_present` (relational booleans — derived, not stored in v1)

Both are **booleans**, and both are **relational**, so v1 does **not** store them as datum
cells — they are derived when the registry is projected/exported:

- `active`/status — an entity is *live* when it (or its instance) has a **non-refused
  contract** with the registry (`mycite.portal.contract.v2`), else *still* (a curated listed
  profile) or *listed* (a directory record). The publisher
  (`publish_micyte_registry._live_nodes`) derives "live" from the private contract records —
  so the map and the contracts can never disagree. Do not hand-set an `active`/live cell
  independently of its source. (The still/listed split is a curated presentation tier; only
  "live" is contract-derived. A *stored* `active` base-2 bit remains deferred — see below.)
- `dns_present` — `false` until a machine-readable **`micyte-<msn_id>.bin`** card is served
  at the site root (none exist yet — the served-card exporter is posture); the
  `website`/`dns` string is carried regardless. Derived by probing for the artifact.

A *stored* bit for either would need a net-new base-2 radix — there is none today, and the
existing `niu-baciloid`s build on a base-256 SAMRAS numeral system, so minting a base-2
SAMRAS substack on the live anchor is deferred as a future refinement. It buys nothing while
both values are relational. The addresses stay reserved (`active` 3-1-20, `dns_present`
3-1-25); the stored card carries `msn_id`, `lcl_id`(=entity_kind), `dns`, `email`, `ipv4`,
`ipv6`, `website`.

## The `registry` card document

The registry publishes its cards as **one flat, type-agnostic datum document** —
`registry` — with **one row per msn contact card**, keyed by `msn_id`. It is *not* split by
kind: a single directory holds legal, natural, administrative and informal cards alike, and
a row's kind is read from its `lcl_id` (→ its depth-3 network kind), never from which document it
lives in. This generalizes the seed `msn_registry` doc (msn_id ↔ name) into the full
contact-card directory a browser reads and a `micyte-<msn_id>.bin` encodes.

## The card vs the profile

**Contact card** — the publishable subset (one `registry` row), all stored plaintext over
`niu-baciloid-256-64`, empty when absent:

```
{ msn_id(self), lcl_id(→type = entity_kind), dns, email, ipv4, ipv6, website }
```

`active` and `dns_present` are appended at projection time (relational — see above), not
stored on the row. The card is the one projection an entity publishes; the registry resolves
the address and points a caller at it, and nothing more.

**Profile** — the per-kind document (`legal_entity` / `natural_entity` /
`administrative_entity`), joined by `msn_id`, extends the card with the rest of the
standardized public detail: `title`, `coordinate`, `common_name`, `visual`,
`jurisdiction_type`, geo/boundary references, **`primary_personnel_msn_id`** (an msn_id
ref, `legal`/`natural` only) and **social links**. The last two live only in the profile,
never the card. Richer per-kind extensions (e.g. the farm package) are separate datum
documents that reference the same `msn_id`; a tool resolves the base profile, then pulls
the extension on top.

## Wire form

Both the card and the profile are ordinary datum documents, so both serialize to the
binary **MSS** form (`mos.mss_binary_v2`) and hash to a `stl.<msn_id>.<name>.<hash>`
document. A site MAY publish its card as a served `micyte-<msn_id>.bin` artifact (an
MSS-encoded card document), letting a frontend consume it as the core of a contact-card
node network — analogous to `robots.txt`/`sitemap.xml`, but machine-first.

## Open reconciliations (must be decided before data migration)

1. **`title` width** — canonical 64; some anchors store 32. Widening is value-preserving.
2. **`dns` base/width** — canonical base-256 × 255; some anchors store octal base-8.

(`entity_kind` is **resolved**: it is the card's `lcl_id` → its depth-3 network kind — one
canonical mechanism, no new field.)

## Non-goals (v1)

- Sub-types of legal entities.
- The farm-package extension of the profile.
- Transport/crypto/handshake and the over-the-network registry listing (the network
  *module*); this document standardizes the *data*, not the wire protocol.
