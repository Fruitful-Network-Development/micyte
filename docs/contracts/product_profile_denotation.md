# What a product profile IS

**Decision: a client's "product profile" is an `offering_record` row.** Not a fourth
record, not the twelve-field agro_erp shape, and not an `offer`.

This document exists because "product" named three unconnected things in this repo and a
request to *"let TFF create product profiles and keep track of inventory"* could have been
answered by minting a fourth. It states which of the three it is, why, and what was
measured on the live store (the FND authority database,
read-only, 2026-09-02) to decide.

## The three candidates, as they actually stood

| | shape | who READS it | who WRITES it |
|---|---|---|---|
| `offering_record` archetype | `lcl_id, txa_id, title, hyphae_ref` (layer 4) | `micyte/channels/agnet.py` (`_product_titles`), by marker | `fnd_app/scripts/build_market_product_profiles.py` — a script |
| agro_erp `product_profiles` rows | 12 value-group pairs (`product_id … propagule_density`) | `product_document_view.build_product_rows` and its three consumers | nobody — an offline ingest, retired |
| `offer` archetype | `lcl_id, price, nominal?, title?` | Brevat's Offering tab, `offer_catalog`, the commerce port | `set_offer` (`ledger_write_runtime`) |

### `offering_record` is not unread, and its 217 rows are agnet's `product_profiles`

The archetype's own note says "A product offering. 217 live rows"
(`scripts/mint_archetype_sandbox.py:357`). Three independent facts pin where those rows
are:

* `micyte/channels/agnet.py`'s header: the lexicon "collapsed 2,643 County Line strings
  into **217** products";
* `datum_row_semantics` holds **218** rows for
  `lv.<fnd msn>.agnet.product_profiles.…` — one `0-0-1` header plus **217**
  rows at `4-12-*`, which is exactly the family `agnet._product_titles` scans;
* `build_market_product_profiles.py` writes each of those rows as
  `[addr, rf.3-1-5 product, rf.3-1-1 taxon, rf.3-1-2 title, rf.3-1-28 hyphae_ref]` — cell
  for cell, `offering_record`.

So the premise that nobody reads `offering_record` was wrong. `agnet.py` reads it; it
simply never names the archetype, because it reads markers rather than asking the
registry. What `offering_record` has never had is a writer a *client* can reach: the only
one is a `--apply` script with `_DEFAULT_DB` pointed at the live store.

### The twelve-field agro_erp shape is not an archetype and has no subject

* It is a **datum template**, not a minted archetype:
  `micyte/data_templates/product_profile.yaml` declares
  `archetype: agro_erp_product_profile_row`, and that token appears in
  `mint_archetype_sandbox.py` **zero** times. It is document metadata
  (`datum_template_archetype`), which the palette reads and `covers()` never sees.
* `record_spec.OWNED_ELSEWHERE["product"]` refuses letting a tenant declare a `product`
  record type in data, on the grounds that "the product ingest" already writes those rows
  positionally. That ingest is `ingest_agro_erp_product_profiles` — a script that no
  longer exists in this tree.
* **There are zero such documents in the live store.** Every row in `documents` whose
  `name` contains `product` is either FND's `agnet.product_profiles` (the
  `offering_record` rows above) or `archetype.kind_product_profile` (the class document).
  `fnd_app/scripts/strip_farm_simulation.py` deleted `product_profiles` — and the
  `1-1-5-*` product identities out of the lcl with it — from the farm it was built for.

A denotation whose readers are four modules and whose instances are zero is a reader
family with no subject. Giving it a writer would resurrect a positional twelve-pair format
whose ingest is gone.

### An `offer` is a price, not a product

`mint_archetype_sandbox.py:361` already says it: an offer is "distinct from
`offering_record` above, which describes a product structurally and carries no price". The
`offer` row's `lcl_id` points at a *classification node*, and `OfferLedger` fills that
select from `_lcl_options` — "the sandbox's OWN classification nodes". Nothing anywhere
said what that node **is**: which taxon it belongs to, or what it is called as a product
rather than as a class. That gap is exactly `offering_record`'s four cells.

## Why `offering_record`

1. **The class library already says so.** `mint_class_library.py:164` —
   `Klass("product_profile", parent="profile", members=("offering_record",))`. A class is
   the layer that says what a row *is*, and `product_profile` has exactly one member. The
   twelve-field shape is in no class, because it is in no archetype.
2. **It is minted, in-corpus, classed and viewscoped** — `record_line` over
   `lcl_id / txa_id / title` (`mint_archetype_sandbox.py:691`). Nothing new to mint, so
   nothing to glyph and no shape for two archetypes to claim.
3. **Its arity is the question a client is actually asking.** "This node of mine is a
   product, it is this taxon, and this is its name" — and the taxon citation is carried
   twice on purpose (`rf.3-1-1` the coordinate, `rf.3-1-28` the row), which is the only
   arrangement in which a bad taxonomy cascade leaves evidence.
4. **It is the join `offer` already points at.** An offer names an lcl node; a product
   profile says what that node is. Nothing about the Offering tab changes.

## The shape mismatch, measured

A client instance (its msn elided here) holds the farm. Its documents, in full:

```
brevat / 1-1-1   anchor   invoices   lcl_domain   offering   plantings   sales
pim    / analytics   anchor   contacts   lcl_domain
system / 2-1-1  agnet-…  anthology  calendar  farm_profile  grantor-…
         lcl_domain  msn_profile  object_profiles  sources
```

Three things follow, and together they are the whole reason the Products tab is blank:

* **The Brevat install landed in a sandbox named `brevat`**, as `AppSandbox` intends and as
  `bootstrap_farm_sandbox.py` records ("two [instances] name a sandbox `brevat`"). The
  four ledger documents are there.
* **`product_document_view.py:145-159` resolves `product_profiles` inside the *active*
  sandbox** — so on the Products tab it looks in `brevat`. Correct code.
* **But the document is not in the other sandbox either.** Trapp holds no
  `product_profiles` anywhere, in `brevat` or in `system`, because
  `strip_farm_simulation.py` deleted it. So the tab was never going to fill: this is not a
  sandbox mismatch, it is an absent document with no writer that could ever create one.

`ABSENT` and `UNPROVISIONABLE` are different states, and this was the second. The fix is
therefore both halves: the package must *provision* the document, and a declared write must
be able to *append* to it.

## What was built

* `offering_record` rows are appended by **`add_product`**
  (`fnd_app/instances/_shared/runtime/ledger_write_runtime.py`), through the same
  `_append_checked` pre-write shape check every modern ledger write passes — a row that
  would fold to something `offering_record` does not cover is refused rather than stored.
* The write is DECLARED by **`ProductCatalog`** (`micyte/tools/ledger_books.py`):
  `DeclaredWrite(document_kind="product_profile", action="add_product")`. An undeclared
  action is denied and has no document kind to measure a grant against.
* `ProductCatalog` is **Brevat's Products tab**, replacing `ProductDocumentViewer` there.
  That viewer was already retired as a tool ("renders a document's own values, which is a
  viewscope's job") and survives as the library `build_product_rows` — which keeps feeding
  `_consumption` and the Flora & Fauna table untouched.
* The Brevat **package** now declares `product_profiles`, so installing it provisions the
  document instead of leaving a tab that cannot be filled.

### The reader is shape-filtered, and `build_product_rows` now refuses foreign rows

`product_profiles` can now hold `offering_record` rows in a farm sandbox, and
`build_product_rows` is **positional**: it maps pair *i* to `_PAIR_FIELDS[i]` regardless of
marker. Read that way an `offering_record` row's `title` babelette lands under
`rotation_group` and its `hyphae_ref` under `propagule` — the "two subtly different row
shapes in one document" failure `record_spec.py` names.

So the two readers are separated the way the ledger separates `invoice` from `offer`:

* `ProductCatalog` reads by SHAPE (`archetype.covers(row_shape(...))`), exactly as
  `offer_rows` does;
* `build_product_rows` now skips any head shorter than the nine pairs its template
  defines. It reads a fixed positional format, so a head that cannot carry that format is
  not a row of it.

### What was deliberately NOT done

* **No fourth archetype.** Nothing was minted, so `mint_archetype_sandbox.py --db` was not
  run and `--apply` was never a possibility.
* **No taxon invented.** `build_market_product_profiles` writes an empty `rf.3-1-1` for a
  product with no taxon rather than "a plausible one", and `add_product` does the same.
  The marker is always written — the shape needs it — the magnitude only when the
  sandbox's own `txa` defines the node.
* **No cross-sandbox taxonomy binding.** A client with no `txa` document gets an empty
  taxon picker, which is the honest state: you cannot cite a taxon you do not hold.
  Binding `taxonomy.txa` as a declared source is the follow-on, and it is
  `sources_manager`'s decision to make with the verdict in front of an operator, not an
  install's.
