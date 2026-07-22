# Datum Editing Atomicity

## Status

Canonical

## Purpose

Define the formal algorithm for datum insertion, deletion, and iteration-shift within
a datum document, including top-down domino ordering, reference cascading, and
magnitude-ordering restoration.

This contract is upstream of:
- `micyte/core/datum_editing/__init__.py` (implementation)
- `micyte/adapters/sql/datum_semantics.py` (adapter layer)
- `fnd_app/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py` (entry point)

---

## Address Format

Every datum in a document is identified by a three-part address:

```
<layer>-<value_group>-<iteration>
```

- **layer**: non-negative integer; identifies the structural tier
- **value_group**: non-negative integer; partitions datums within a layer
- **iteration**: positive integer, contiguous from 1; identifies ordering within (layer, value_group)

Example: `0-0-3` = layer 0, value_group 0, iteration 3.

**Iteration contiguity invariant:** After any edit, all iterations within a
(layer, value_group) family must be contiguous starting at 1. No skips permitted.

---

## INSERT

**Operation:** Insert a new datum at position `(L, V, I)` within an existing document.

**Algorithm:**

1. **Identify the target family** `(L, V)` — all existing datums where address starts with `<L>-<V>-`.

2. **Shift upward (top-down domino order):**
   - Collect all datums in family `(L, V)` with `iteration >= I`.
   - Sort descending by iteration (highest first).
   - For each datum in that order, rename its address from `<L>-<V>-<k>` to `<L>-<V>-<k+1>`.
   - This top-down order prevents address collisions mid-shift: the highest iteration
     is renamed first, creating a free slot below it.

3. **Cascade references:**
   - Build a remap dict: `{ "<L>-<V>-<k>": "<L>-<V>-<k+1>" }` for all shifted datums.
   - Scan every datum in the document (all families, all layers).
   - In each datum's raw payload, replace all occurrences of old addresses with new addresses.
   - Reference forms to remap: bare address (`0-0-2`), reference token (`rf.0-0-2`),
     qualified reference (`<numeric-hyphen>.0-0-2`).

4. **Insert the new datum** at address `<L>-<V>-<I>`.

5. **Recompute version identity:**
   - Sort all datums by `(layer, value_group, iteration)` (numeric ascending).
   - Compute SHA256 of sorted row payloads → `version_hash`.
   - Recompute `hyphae_chain` including rudi datum prefix.

**Postcondition:** Family `(L, V)` has iterations `1 .. N+1`; new datum is at position `I`.

---

## DELETE

**Operation:** Remove the datum at address `(L, V, I)` from a document.

**Pre-check:** If any datum outside family `(L, V)` holds a reference to `<L>-<V>-<I>`,
the delete is **rejected** with an error listing the referencing addresses. This prevents
dangling references.

**Algorithm:**

1. **Remove the target datum** at address `<L>-<V>-<I>`.

2. **Shift downward (top-down domino order):**
   - Collect all datums in family `(L, V)` with `iteration > I`.
   - Sort ascending by iteration (lowest first).
   - For each datum in that order, rename `<L>-<V>-<k>` to `<L>-<V>-<k-1>`.
   - Ascending order is correct for delete: the slot at I+1 is moved to I first,
     avoiding collisions with the now-deleted slot below.

3. **Cascade references** (same process as INSERT step 3):
   - Build remap dict: `{ "<L>-<V>-<k>": "<L>-<V>-<k-1>" }` for all shifted datums.
   - Scan all datums; replace old addresses with new in all reference forms.

4. **Recompute version identity** (same as INSERT step 5).

**Postcondition:** Family `(L, V)` has iterations `1 .. N-1`; no dangling references remain.

---

## MOVE (Shift)

**Operation:** Move a datum from address `(L, V, I_src)` to position `(L, V, I_dst)` within
the same family. Implemented as a DELETE from `I_src` followed by an INSERT at `I_dst`
(with `I_dst` adjusted for the deletion shift if `I_dst > I_src`).

---

## Top-Down Domino Order — Rationale

Shifting must proceed from the highest iteration downward (for INSERT) or from the
lowest upward (for DELETE) to avoid overwriting a datum with the renamed datum ahead of it.

Example (INSERT at I=2 into family with iterations 1,2,3):
- Sort descending: [3, 2]
- Rename 3 → 4: family is now [1, 2, 4]  — slot 3 is free
- Rename 2 → 3: family is now [1, 3, 4]  — slot 2 is free for the new datum
- Insert at 2: family is [1, 2, 3, 4] ✅

If ascending order were used:
- Rename 2 → 3: collides with existing 3 → family is [1, 3, 3] ❌

---

## Reference Cascading

Every datum's raw payload is scanned after an iteration shift. References appear in
three forms, all of which must be remapped:

| Form | Example | Remapped to |
|---|---|---|
| Bare address | `0-0-2` | `0-0-3` |
| Reference token | `rf.0-0-2` | `rf.0-0-3` |
| Qualified reference | `<prefix>.0-0-2` (where prefix is numeric-hyphen) | `<prefix>.0-0-3` |

The remap dict is built from the shift results and applied atomically to all payloads
before any version identity is recomputed.

---

## Magnitude Ordering Invariant

Datums within the same immediate family are ordered such that a datum whose referenced
magnitude is larger comes later. This invariant is maintained implicitly by the
contiguous iteration numbering: the caller is responsible for inserting at the correct
position `I` that preserves magnitude order. The insert/delete primitives do not
independently verify magnitude ordering — they only maintain contiguity.

After any edit that changes reference structure, the caller should verify that the
resulting family ordering still satisfies the magnitude invariant before committing.

---

## Atomicity Boundary

The SQL adapter (`datum_semantics.py` → `datum_store.py`) wraps all row mutations in a
single SQLite transaction:
- All shifted address updates
- All reference cascade updates  
- The new/deleted datum row
- The updated `datum_document_semantics` row (version_hash + hyphae_chain)

If any step fails, the entire transaction rolls back. The document remains in its
pre-edit state.

**Preview vs Apply:** The adapter supports a two-phase model:
- **Preview:** Compute the shifted rows and remap in memory; return a diff without writing.
- **Apply:** Execute the preview and commit to the database.

---

## Implementation References

| Component | File | Lines |
|---|---|---|
| Pure edit functions | `micyte/core/datum_editing/__init__.py` | all |
| Insert/delete driver | `micyte/adapters/sql/datum_semantics.py` | 463–573 |
| SQL apply | `micyte/adapters/sql/datum_store.py` | 761–818 |
| Version identity | `micyte/adapters/sql/datum_semantics.py` | 133–328 |
| Workbench entry | `fnd_app/instances/_shared/runtime/portal_datum_workbench_mutation_runtime.py` | 180–199 |
| Unit tests | `fnd_app/tests/unit/test_datum_editing.py` | all |

---

## Non-Goals

- This contract does not define SAMRAS tree-level mutations (add_child, move_branch).
  Those are governed by `micyte/core/structures/samras/mutation.py`.
- This contract does not define cross-document reference resolution. References that
  cross document boundaries are out of scope for the iteration-shift algorithm.
- This contract does not define the canonical form of datum payloads — only the
  addressing and cascading rules.
