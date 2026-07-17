"""Rudimentary datum-document manipulation operations + cross-doc workbook model.

A pure (store-agnostic) library of composable operations over MOS datum
documents, built on the trusted intra-document reorder engine
(:mod:`micyte.core.datum_semantics`) and the SAMRAS codec.
A sandbox loads as a :class:`Workbook` (named sheets); operations transform it
in memory and a single store-bound executor persists the cascade.
"""

from __future__ import annotations

from . import workbook as workbook_codec
from .compiler import compile_workbook
from .migrate import (
    MigrationError,
    MigrationPlan,
    TouchedSheet,
    mint_canonical_id,
    plan_migration,
)
from .node_ops import (
    DropNode,
    MintNode,
    RebuildCollection,
    RecompileMagnitude,
    RelocateNode,
    RenameNode,
    RepointNode,
    RewriteRefs,
)
from .ops import (
    DeleteRow,
    InsertRow,
    MoveRow,
    ReorderRow,
    Workbook,
    WorkbookDelta,
    apply_sequence,
)
from .refs import (
    DefinedNode,
    Edge,
    ReferenceIndex,
    build_reference_index,
    defined_node_addrs,
    is_node_addr_reference,
    is_reference_marker,
)
from .rules_loop import StepReport, check_step

__all__ = [
    "Workbook",
    "WorkbookDelta",
    "apply_sequence",
    "InsertRow",
    "DeleteRow",
    "MoveRow",
    "ReorderRow",
    "Edge",
    "DefinedNode",
    "ReferenceIndex",
    "build_reference_index",
    "defined_node_addrs",
    "is_reference_marker",
    "is_node_addr_reference",
    "MintNode",
    "RelocateNode",
    "RepointNode",
    "RenameNode",
    "DropNode",
    "RewriteRefs",
    "RecompileMagnitude",
    "RebuildCollection",
    "StepReport",
    "check_step",
    "MigrationError",
    "MigrationPlan",
    "TouchedSheet",
    "mint_canonical_id",
    "plan_migration",
    "compile_workbook",
    "workbook_codec",
]
