"""Pure migration planner: ops → re-minted, rule-checked, ready-to-write cascade.

``plan_migration`` runs an op sequence over a baseline :class:`Workbook` (no
store, no writes), determines the touched-sheet cascade, re-mints each touched
sheet's canonical document id from its new MSS hash, runs the rule-check loop,
and asserts SAMRAS magnitudes match their source node sets. The store-bound
executor (:mod:`adapters.sql.datum_workbook_apply`) consumes the resulting
:class:`MigrationPlan` to back up, write, and verify.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from micyte.core.datum_documents import AuthoritativeDatumDocument
from micyte.core.document_naming import (
    format_canonical_document_id,
    parse_canonical_document_id,
)
from micyte.core.mss import compute_mss_hash
from micyte.core.structures.samras.codec import decode_canonical_bitstream

from .ops import Workbook, apply_sequence, order_sheets
from .refs import defined_node_addrs
from .rules_loop import check_step
from .samras_deps import (
    SAMRAS_ROOT_REF,
    check_denotation,
)


class MigrationError(RuntimeError):
    """Raised when a planned migration fails its rule-check or SAMRAS consistency."""


def mint_canonical_id(doc: AuthoritativeDatumDocument) -> tuple[AuthoritativeDatumDocument, str]:
    """Re-mint a document's canonical id from its current MSS hash.

    The single extraction of the placeholder→``compute_mss_hash``→re-mint idiom
    copy-pasted across the ingest/promote/bootstrap scripts and the mutation
    runtime. Naming parts (prefix/msn/sandbox/name) are read from the document's
    existing canonical id; the hash is content-derived (id is not hashed), so an
    unchanged document re-mints to the same id (idempotent).
    """
    parsed = parse_canonical_document_id(doc.document_id)
    version_hash = compute_mss_hash(doc)["version_hash"]
    if version_hash.startswith("sha256:"):
        version_hash = version_hash[len("sha256:"):]
    new_id = format_canonical_document_id(
        prefix=parsed.prefix,
        msn_id=parsed.msn_id,
        sandbox=parsed.sandbox,
        name=parsed.name,
        version_hash=version_hash,
    )
    return replace(doc, document_id=new_id), version_hash


@dataclass(frozen=True)
class TouchedSheet:
    name: str
    prior_id: str
    new_document: AuthoritativeDatumDocument
    new_hash: str


@dataclass
class MigrationPlan:
    sandbox: str
    final_workbook: Workbook
    touched: dict[str, TouchedSheet] = field(default_factory=dict)
    write_order: list[str] = field(default_factory=list)
    expectations: dict[str, Any] = field(default_factory=dict)
    advisories: list[str] = field(default_factory=list)




def plan_migration(baseline: Workbook, ops: list[Any]) -> MigrationPlan:
    final, _deltas = apply_sequence(baseline, ops)

    # rule-check the final workbook (HARD issues abort the plan)
    report = check_step(final)
    if not report.ok:
        raise MigrationError("rule-check failed:\n  " + "\n  ".join(report.hard))

    # SAMRAS consistency: each anchor magnitude must match its source node set.
    #
    # Coverage is DISCOVERED (samras_deps.check_denotation) rather than looked up in a
    # per-sandbox address map, so every sandbox and every *-SAMRAS structure is examined —
    # the old map described the agro_erp anchor and silently examined nothing at all in the
    # registrar, whose lcl magnitude sits at 1-1-6.
    #
    # A finding aborts the plan only when THIS migration is responsible for it: a divergence
    # that was already in the baseline is a pre-existing corpus condition, and failing an
    # unrelated migration over it would hold every future edit hostage to someone else's open
    # decision. Those become advisories, which the mutation runtime already surfaces.
    samras_advisories: list[str] = []
    if "anchor" in final.names():
        final_sheets_by_name = {name: final.sheet(name) for name in final.names()}
        for finding in check_denotation(final.sheet("anchor"), final_sheets_by_name):
            if finding.status in ("coherent", "unpaired"):
                continue
            source = finding.structure
            baseline_set = (
                defined_node_addrs(baseline.sheet(source))
                if source in baseline.sheets else set()
            )
            caused = baseline_set != defined_node_addrs(final_sheets_by_name[source])
            if not caused:
                samras_advisories.append(f"pre-existing: {finding.summary()}")
                continue
            if finding.status == "uncompilable":
                raise MigrationError(
                    f"{source} node set is not SAMRAS-encodable: {finding.detail}")
            raise MigrationError(
                f"SAMRAS {finding.magnitude_addr} does not match the current {source} node "
                f"set — a RecompileMagnitude is missing"
            )

    # determine the touched-sheet cascade + re-mint canonical ids
    touched: dict[str, TouchedSheet] = {}
    expectations: dict[str, Any] = {"row_counts": {}, "samras": {}}
    final_sheets: dict[str, AuthoritativeDatumDocument] = {}
    for name in final.names():
        doc = final.sheet(name)
        new_doc, new_hash = mint_canonical_id(doc)
        final_sheets[name] = new_doc
        baseline_doc = baseline.sheets.get(name)
        prior_id = baseline_doc.document_id if baseline_doc is not None else ""
        # Touched iff CONTENT changed — not merely a stale stored id. (A doc whose
        # stored id doesn't match its content hash is a pre-existing inconsistency to
        # reconcile separately, not silently rewritten by an unrelated migration.)
        baseline_hash = (
            compute_mss_hash(baseline_doc)["version_hash"].removeprefix("sha256:")
            if baseline_doc is not None
            else None
        )
        if baseline_hash != new_hash:
            touched[name] = TouchedSheet(name=name, prior_id=prior_id, new_document=new_doc, new_hash=new_hash)
            expectations["row_counts"][name] = len(new_doc.rows)
    # samras roundtrip expectations (closure sizes) for verify
    if "anchor" in final_sheets:
        for row in final_sheets["anchor"].rows:
            raw = row.raw
            if isinstance(raw, list) and raw and isinstance(raw[0], list) and len(raw[0]) >= 3 and str(raw[0][1]) == SAMRAS_ROOT_REF:
                expectations["samras"][row.datum_address] = len(decode_canonical_bitstream(str(raw[0][2])).addresses)

    return MigrationPlan(
        sandbox=baseline.sandbox,
        final_workbook=replace(final, sheets=final_sheets),
        touched=touched,
        write_order=order_sheets(touched.keys()),
        expectations=expectations,
        advisories=[*report.advisory, *samras_advisories],
    )
