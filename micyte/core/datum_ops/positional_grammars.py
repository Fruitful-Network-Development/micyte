"""Documents whose row families name a ROLE, not an arity — rows a positional reader owns.

I7 ("the address is the arity": a layer-4 row with *n* pairs lives in family ``4-n``) is the
local-domain convention, and the readdress converts a document to it one at a time. Two
grammars in this package read their rows BY FAMILY instead, and say so at the top of their
modules:

* the class library (:mod:`archetype_class`): header ``4-1``, members ``4-2``, slots ``4-3``;
* the viewscopes (:mod:`viewscope`): container ``4-1``, slots ``4-2``.

There a three-pair slot row lives at ``4-2`` because it IS a slot, not because it has two
pairs. Moving it to ``4-3`` does not convert the document — it blinds the reader. That
happened on 2026-09-30: the archetype-library readdress moved 63 of these documents with
the archetypes, every viewscope pane drew zero groups and the calendar found zero logs while
the archetype registry parsed identically, and the library was restored.

The rule lives here once. The readdress refuses these documents and the audit reports them
apart, both by asking :func:`positional_grammar`. The key is the document NAME because that
is how the two readers find their documents: ``archetype_class`` says nothing may be named
``kind_*`` but a class, and ``viewscope`` names one viewscope per archetype.
"""

from __future__ import annotations

from .archetype_class import CLASS_PREFIX
from .viewscope import VIEWSCOPE_PREFIX

#: ``(document-name prefix, the grammar that owns the rows)``.
POSITIONAL_GRAMMARS: tuple[tuple[str, str], ...] = (
    (CLASS_PREFIX, "class library (archetype_class: header 4-1, members 4-2, slots 4-3)"),
    (VIEWSCOPE_PREFIX, "viewscope (container 4-1, slots 4-2)"),
)


def positional_grammar(document_name: str) -> str:
    """The grammar that owns this document's row families, or ``""`` when I7 applies."""
    name = str(document_name or "")
    for prefix, grammar in POSITIONAL_GRAMMARS:
        if name.startswith(prefix):
            return grammar
    return ""


__all__ = ["POSITIONAL_GRAMMARS", "positional_grammar"]
