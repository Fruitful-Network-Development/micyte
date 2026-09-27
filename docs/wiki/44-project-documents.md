# 44 — Project Documents

> Status: as-built (2026-09-11: archetypes, class, reader, writer, the export and the
> document-backed edit — the plan `TASK-2026-09-11-001.project-document-convention.plan.md` in the agentic tree)
>
> [← Overview](00-overview-and-glossary.md)

## The one idea

A project is a DOCUMENT on the instance's tree, and a website's own resolver reads it. The
operator's brief (2026-09-11): *"a website can have its own custom reader or resolver such
that any design can be the shown result, but the extent of information can be made dynamic
and yet also expected."* Both halves are held by the same rule the local domain rests on —
[the address is the arity](43-local-domain-log.md): a document's row COUNT varies while no
row's arity does. A project with forty photographs and one with three are the same four
shapes, forty and three times.

## The four rows

Declared in `scripts/mint_archetype_sandbox.py`, members of the `project` class
(`scripts/mint_class_library.py`), read by `micyte/core/datum_ops/project_document.py`.

| archetype | cells, in order | one row per |
|---|---|---|
| `project_profile` (the header) | msn_id owner · site_msn where · lcl_id kind · title name · utc? opened · status_ref? standing · hyphae_ref? owner's profile | document |
| `project_text` | lcl_id ROLE · nominal order · title text | paragraph, fact line |
| `project_artifact` | lcl_id SLOT · lcl_id ROLE · nominal order · title? caption | picture, tour |
| `project_fact` | nominal value · lcl_id KIND · title? word | detail |

Three things the table encodes on purpose:

* **The header is `project_profile`, widened.** The `projects` document's rows were already
  this shape; the two new cells are optional and LAST, so every row written before them
  keeps its cover and a project document's header is the same thing as a project row.
* **Roles and kinds are NODES.** `feature`, `gallery`, `tour`, `plan`, `hidden`; `summary`,
  `story`, `fact`; `beds`, `baths`, `square_feet` … are labels of nodes under the instance's
  `classes`, seeded by the convention so a resolver can rely on them, and extendable by the
  instance without a new shape. A row carries the node; the reader names it from the tree.
* **Cell order is the shape.** `lcl_id,title[,nominal]` belongs to `class_record` and
  `lcl_id,nominal+` to `job_service`, so a text is `lcl_id,nominal,title` and a fact is
  `nominal,lcl_id[,title]`; an artifact's two lcl cells are a run read positionally — slot,
  then role — exactly as `local_domain_log`'s are. `ArchetypeRegistry.ambiguities()` is
  empty with all four minted, and a test holds it there.

## Expected, then dynamic

`read_project(document, registry=, namespace=, labels=)` answers a `ProjectView` with FIXED
keys — `title kind owner site opened status owner_profile`, `texts{role: [{order, text}]}`,
`artifacts{role: [{slot, order, caption}]}`, `facts{kind: {value, word}}` — and two more that
carry what it does not know: `extras{archetype: [{address, fields}]}` for rows of any OTHER
archetype the registry covers, and `unmatched[address]` for rows nothing covers. Nothing is
dropped and nothing is guessed at.

**When the base cannot say it, abstract a new archetype from it.** A site that needs a
shape the four cannot express — a listing's price history, a floor plan's rooms — does not
widen an owned shape ([an archetype cannot be loosened into a shape that is owned]) and does
not wedge the fact into a caption. It mints a DERIVED archetype in the library
(`Archetype("project_listing", …)`) as a member of the `project` class, the partition still
holds (every archetype in exactly one leaf class), and the reader carries its rows under
`extras["project_listing"]`. The site's resolver is the only thing that has to learn it,
which is the point: the base stays predictable for every other reader.

## Where the pictures are

A `project_artifact` names an artifact SLOT — a node under the tree's `artifacts › image`
(or `video`) kind whose `art.` document holds the bytes (`file_artifact`,
`fnd_app/instances/_shared/runtime/domain_document_runtime.py`). The site does not read
the bytes from the books; the export writes the picture beside the site's assets and the
document's view names it by slot, so a resolver joins slot → file through the export's own
table. One picture, one slot, one row per role it plays.

## The export, and the edit that follows it

`site_hosting.project.export` (`fnd_app/instances/_shared/runtime/utilities_extensions/site_profiles.py`
`export_site_project`; the door prepares it in `project_export_runtime.py`) writes the
view as JSON beside the site's assets (`<date>.datum-project.<slug>.json`, allocated on the
manifest under `project`), lands any picture the site's pool lacks — found by CONTENT: the
site's allocated images are hashed once and a slot whose `art.` document carries the same
sha256 already has its file — and DERIVES the leaflet the pages are generated from
(feature, order, hidden, captions, name, descriptions) through the store's own profile
writer, then rebuilds. The leaflet's fields the document does not say (its kind, card id,
address block) stay as they are.

A paragraph is its LINES: a title babelette holds 64 characters, so `project_text` carries
the paragraph's order and, on a paragraph of more than one line, the line's order
(`lcl_id, nominal+, title`); the reader joins them. `micyte.tools.note_books.wrap_lines` is
the one rule.

Once a profile has been exported, the listing says which document it is derived from
(`project_export_of`, read beside the leaflet), and a `profile.edit` on that profile is
performed on the DOCUMENT (`project_edit_runtime.py`: the page's names resolve to refs
as before, the export's own pictures table says which slot each ref is) and exported
again — the page posts what it always posted; the source moved under it. An upload
through the page files the picture into the books and into the document's gallery in
the same step.

BHN's four homes were migrated by `fnd_app/scripts/migrate_leaflets_to_project_documents.py`
(rehearsed on a copy first: the derived leaflets and the site's `properties.js` came out
identical).

## See also

* [`41-archetypes-and-viewscopes.md`](41-archetypes-and-viewscopes.md) — why an archetype
  is a blank instance and how a view is declared as data.
* [`43-local-domain-log.md`](43-local-domain-log.md) — the tree a project document is filed
  on, and the convention document every tree pins.
