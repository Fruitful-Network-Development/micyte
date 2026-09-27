# What lives in the registrar sandbox

**Status:** adopted 2026-08-09 (phase 1), audited and amended by phase 5,
event logs decided 2026-08-10 (phase 4).
Enforced by `fnd_app/tests/architecture/test_registrar_residency.py`, which fails when a
registrar document is unclassified and when the pending-move list goes stale.

Phase 3b landed 2026-08-09: both **Moves** documents are now
`agnet/member_profiles` and `agnet/member_ag_profiles`. They were RENAMED, because
`FARM_SHAPE = {anchor, farm_profile}` would otherwise have made the channel classify as a
farm. With the registrar no longer holding one, `is_farm` dropped its
`not is_directory_keeper` clause — the workaround disappeared, which is the check this rule
set itself.

The registrar abstracts **resources**. It says what an address IS, what it is called, where
its boundary runs, and which entities are defined — and nothing about what any party is
*doing*. Activity belongs to a channel; a party's own working documents belong to its
instance.

Three rules, in the order they decide:

1. **A document about an ADDRESS or a BOUNDARY stays.** These are the things every other
   sandbox reads and none of them owns.
2. **A document about a PARTY'S ACTIVITY moves to the channel.** A farm profile is not a
   fact about an address; it is a fact about an operation, and operations belong where the
   unengaged case can also live.
3. **A document that DEFINES an entity stays; a document that PROFILES one moves.** The
   registrar answers "who is this msn", the channel answers "what do they run".

---

## The classification

Measured against the live store: **484 documents — 479 stay, 2 move, 3 open.**
(Phase 1 counted 478/4; the phase 5 audit reclassified `247_17_77` from stays to open;
phase 4 moved `qc_log`/`hc_log` from open to stays on the operator's decision.)
Machine-readable copy:
the task's evidence (`registrar-channel-separation/phase1/residency.json` under the agentic tree).

### Stays — 479 documents, 47,529 rows

| document(s) | archetype | rows | why |
|---|---|---:|---|
| `registry` | `msn_contact_card` | 239 | **the msn_id contact-card resource** — the standard the rest of the system reflects |
| `address_nodes` | `record` | 42,003 | name table: address → name |
| `administrative` | `record` | 2,696 | name table for the region nodes above the streets |
| `msn_registry` | `record` | 2 | name table |
| `administrative_entity` | `administrative_entity_profile` | 53 | the admin entity profiles |
| `legal_entity` | `legal_entity_profile` | 163 | entity **definition** entry |
| `natural_entity` | `natural_entity_profile` | 26 | entity **definition** entry |
| `lcl_domain`, `lc_log` | `class_record` | 78 | the registrar's own classification space (renamed from `lcl` 2026-08-20) |
| `anchor` | — | 83 | the sandbox's abstraction rows |
| `qc_log`, `hc_log` | `event_log_entry` | 191 | **the events the public calendar reads** — see below |
| 467 boundary documents | `geospatial_polygon` | 1,995 | boundary geometry — a resource, each NAMED for the node it outlines |

`legal_entity` and `natural_entity` stay **as definitions**. Rule 3 is what keeps them: a
row saying *this msn is a legal entity called X* is the registrar answering "who is this
address". A row saying *X runs a 40-acre operation with these fields* is not, and there is
none here today.

### Moves — 2 documents, 320 rows

| document | archetype | rows |
|---|---|---:|
| `farm_profile` | `farm_profile_identity` | 139 |
| `fnd_ag_profiles` | `ag_profile` | 181 |

**The code already carries an exception for exactly these.** `SandboxInstance.is_farm` is

```python
FARM_SHAPE <= self.document_names and not self.is_directory_keeper
```

and the comment above it says why: *"The registrar carries an `anchor` AND a document named
`farm_profile`"*. Measured — `registrar.is_farm` is `False` today **solely** because of
that clause. The exception exists to compensate for a mislocated document, so moving the
document is what makes it stop being load-bearing. That is the check on this rule: if the
move is right, a workaround disappears.

**`qc_log` and `hc_log` stay — decided 2026-08-10.** Rule 2 says a party's activity moves,
and a recurring farm stand looks like activity. It is not, and the deciding evidence is what
already reads them: `micyte.com/js/calendar.js` joins every event to its host's msn contact
card and takes the host's `entity_kind`, defaulting to `legal` — the calendar is a view over
entity DEFINITIONS, which is rule 3's "stays". *When is the Hudson farmers market* is a fact
about a place and its host, answerable whether or not anyone has engaged a channel. Moving
these would make a public page depend on channel state to answer it.

### Open — 3 documents, 478 rows

Left open deliberately. Each is a judgement this phase does not have the evidence to make,
and guessing would put the wrong thing in a contract:

| document | rows | the question |
|---|---:|---|
| `network_sources` | 472 | a source manifest is a RESOURCE others resolve, but its contents are channel-specific. Resource or channel? |
| `channels` | 2 | a channel directory in the registrar is either the resource that lists channels, or channel state that leaked. |
| `247_17_77` | 4 | **found by the phase 5 audit.** Folds to `geospatial_polygon` like the other 467, but is not NAMED for the node it outlines — every sibling is `3-2-3-17-…`. `directory.py` states the convention: *"A boundary document is NAMED for the gazetteer node it outlines, so the catalog itself says which places are drawable."* This one cannot say which place it draws. Someone has to decide which node it belongs to, or that it should go. |

An open document **stays where it is** until it is decided. Moving on a guess is worse than
an unclassified row, because the move is what other readers key on.

---

## Engagement — what makes an instance

**Adopted: (b).** An entity is an **engaged party** when `agnet` holds a `channel_profile`
carrying that party. A farm profile with an msn and no party is a channel account that
nobody has engaged yet — which is the case the platform needs in order to be developed
against real structure without inventing a customer.

This is a change to what an instance *is*. Today `list_sandbox_instances` groups sandboxes
by msn and anything with its own msn is an instance; engagement is not a property of an
address, so the current rule cannot express it. After phase 3, **only engaged parties are
instances**, and the switcher offers only those.

The fact lives in the channel and not in `registrar/legal_entity` because the *unengaged*
case already lives there: a profile that exists without a party is the normal state of a
prospect, and a registrar flag would make the registrar track a relationship rather than a
definition — which is rule 3 the other way round.

`test_sharing_one_msn_would_merge_two_sandboxes_into_one_instance` continues to hold: this
narrows *which* msns count, it does not stop an msn being the key.

---

## How this is checked

The phase 5 audit reads this document and fails on drift:

- every live registrar document is classified here by name or by archetype;
- no farm-shaped document is in the registrar;
- `is_farm` is correct **without** the directory-keeper exception carrying it;
- every instance is an engaged party, and an unengaged channel profile is not offered.

A residency rule that is not machine-checked is a convention, and conventions drift — this
one has a corpus behind it (`residency.json`) so the audit compares like with like.
