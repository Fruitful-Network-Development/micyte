"""The MOS-rule check loop, run after every manipulation op and before finalize.

Three checks, separated into HARD (abort the plan) vs advisory (record, continue):

* **Row shape** — every row must be ``well_formed`` per
  :func:`datum_rules.classify_row` (HARD); soft issues like
  ``value_group_pair_mismatch`` are advisory.
* **SAMRAS magnitudes** — every ``0-0-5``-rooted magnitude must decode as a
  canonical bitstream (HARD). (Whether it matches the *current* node set is only
  asserted at finalize, after :class:`RecompileMagnitude`, since intermediate
  steps legitimately carry a stale-but-valid magnitude.)
* **Reference existence** — every cross-document edge must resolve to a defined
  node, or the ``"0"`` no-reference sentinel (HARD) — the integrity the intra-doc
  engine cannot see.

Row-family contiguity is recorded as advisory (the store persists regardless; only
the intra-doc reorder engine requires it).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from micyte.core.datum_rules import classify_row
from micyte.core.structures.samras.codec import decode_canonical_bitstream
from micyte.core.structures.samras.validation import InvalidSamrasStructure

from .ops import Workbook
from .refs import build_reference_index, markers_for_workbook
from .samras_deps import SAMRAS_ROOT_REF


@dataclass
class StepReport:
    hard: list[str] = field(default_factory=list)
    advisory: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hard


def _magnitude_rows(doc):
    for row in doc.rows:
        raw = row.raw
        if isinstance(raw, list) and raw and isinstance(raw[0], list) and len(raw[0]) >= 3:
            if str(raw[0][1]) == SAMRAS_ROOT_REF:
                yield row


def check_step(workbook: Workbook) -> StepReport:
    report = StepReport()

    # 1. row shape
    for name in workbook.names():
        for row in workbook.sheet(name).rows:
            shape = classify_row(row.datum_address, row.raw)
            if not shape.well_formed:
                report.hard.append(f"{name}:{row.datum_address} malformed ({list(shape.issues)})")
            elif shape.issues:
                report.advisory.append(f"{name}:{row.datum_address} {list(shape.issues)}")

    # 2. SAMRAS magnitudes decode canonically
    for name in workbook.names():
        for row in _magnitude_rows(workbook.sheet(name)):
            bits = str(row.raw[0][2])
            try:
                decode_canonical_bitstream(bits)
            except InvalidSamrasStructure as exc:
                report.hard.append(f"{name}:{row.datum_address} SAMRAS not canonical: {exc}")

    # 3. cross-document reference existence
    #
    # Resolves against this sandbox's own definitions PLUS workbook.external_nodes
    # — the nodes it is declared to reference in another sandbox. Cross-sandbox
    # references are part of the model (a farm's product rows are keyed to taxon
    # nodes owned by the `taxonomy` sandbox), so checking a lone sandbox's
    # definitions reports them all as dangling and aborts the plan.
    # THE MARKERS ARE THIS NAMESPACE'S, resolved once and reported when they are not.
    # Until 2026-09-01 this used the UNION of three namespaces' node-ref markers for every
    # document, and `rf.3-1-1` is `txa_id` in `farm`/`taxonomy` but `coordinate` in
    # `registrar`/`archetype` and `utc` in `system`. Measured across the live store: 162,249
    # dangling references reported out of 163,643 edges — 99.1% false, 162,102 of them
    # coordinates and timestamps. On a HARD check that `datum_workbook_apply` turns into a
    # refusal, that was a live write blocker for every registrar and agnet workbook.
    markers, blind = markers_for_workbook(workbook)
    if blind:
        # ADVISORY, not silent. A fallback run still checks references — it just also
        # flags literals, so its hard failures cannot be trusted without knowing that.
        report.advisory.append(
            f"reference check ran on the UNION of namespace markers ({blind}); "
            "literals typed as coordinates or timestamps may be reported as dangling"
        )
    index = build_reference_index(workbook, markers)
    defined = index.defined_nodes() | set(workbook.external_nodes)
    for edge in index.edges:
        target = edge.target_node_addr
        if target == "0":
            continue
        if target not in defined:
            report.hard.append(
                f"{edge.src_sheet}:{edge.src_row} dangling ref → {target} (marker {edge.marker})"
            )

    return report
