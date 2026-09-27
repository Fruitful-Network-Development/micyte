"""Notes — many small, separate text datum docs, read and written as ARCHETYPE rows.

TASK-2026-08-14-002 Phase 5 (Oveure). The operator's substrate decision: a note is its own
datum DOCUMENT (``note_<slug>``), not a row in a shared log — many small separate docs, in
whatever sandbox the operator is working in. Its rows are the ``text_note`` archetype
minted this phase: title cells and nothing else.

## A note is a sequence of LINES, because that is what the datum layer can hold

The only text the title babelette stores is **printable ASCII, 64 characters per cell**
(``labels.TITLE_BITS``), and ``decode_label`` drops control bytes on the way out — measured
before this was written: ``"a\\nb"`` round-trips to ``"ab"``. So a newline can never live
INSIDE a cell, and the design follows the physics instead of fighting it:

* one row per line, in datum-address order; a blank line is a row whose title decodes
  empty (the encoder stores ``""`` as all padding, honestly);
* a line longer than 64 characters is soft-wrapped at save — **the stored form is
  canonical**, a reread shows exactly the lines that exist, and a second save of the same
  text changes nothing;
* anything outside printable ASCII is refused with the characters named (the
  ``_unencodable`` rule), never transliterated or dropped.

The alternative — raw 64-char chunks rejoined by concatenation — was rejected on that
measurement: it needs newlines inside cells, which the decoder is deliberately built to
strip.

:func:`note_text` is the ONE read model behind every consumer of a writing — the
`ledger_books` rule: two readers of one fact must be one function.

## The NAME convention is gone (2026-08-20)

A writing used to be discoverable by its filename: ``note_2-1-3``, ``note_2-1-3_yes``.
Under the local domain log a writing is a SLOT — an ordinary node on the reserved
``documents`` branch — and the association rides a cell instead. Both conventions were
live for one day and this module carried the older one; the migration left ZERO documents
named ``note_*`` on the corpus, so what remains here is the datum physics above and
nothing about how a document is called.

The Notes SHELF went with it. It listed documents by that prefix, and a shelf that can
only ever be empty is a surface that teaches an operator the tool is broken. Its
capability — write a small text document, read it back — is the Domain surface's, where a
writing is shown ON the node it is about.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops import archetype_shape as ash
from micyte.core.datum_ops.datum_resolve import as_text, decode_label
from micyte.core.datum_ops.labels import TITLE_BITS

from ._viewscope import _row_values

#: The archetype a writing's rows are — imported by the write runtime, never restated
#: (the `JOB_LOG` rule).
NOTE_ARCHETYPE = "text_note"

#: One stored line's budget: the title babelette's width in ASCII characters.
LINE_CHARS = TITLE_BITS // 8

#: One WRITING's budget (the name-first tree, operator 2026-08-15): "for now it should
#: be limited to creating 4096 ACSII nominal datums". Counted on the normalized text
#: (newlines included — they are row structure the reader gets back), refused at save
#: with the overage named. One statement; the form label and the refusal both read it.
NOTE_CHAR_BUDGET = 4096

#: The providers Oveure's ask relay may address — the source of the app manifest's
#: DeclaredCalls and of the ask control's dropdown, stated once. Each is an
#: external-call SERVICE token; the binding and every grant stay the operator's.
OVEURE_PROVIDERS = ("anthropic", "openai")


def unstorable(text: str) -> str:
    """The characters of ``text`` the note substrate cannot hold, or ``""``.

    The storable alphabet is printable ASCII (32–126) plus the newline, which is ROW
    structure rather than cell content. Everything else — tabs, control bytes, the whole
    of Unicode — is named back to the writer, because ``decode_label`` would silently
    drop or mangle it and a note that reads differently than it was written is worse
    than a refusal.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    bad = {ch for ch in text if ch != "\n" and not (32 <= ord(ch) <= 126)}
    return "".join(sorted(bad))


def wrap_lines(text: str) -> list[str]:
    """``text`` as the stored lines: split on newlines, soft-wrap at :data:`LINE_CHARS`.

    Word-aware where a space allows it, hard at the budget where one word overruns it.
    Deliberately IDEMPOTENT: ``wrap_lines("\\n".join(wrap_lines(t))) == wrap_lines(t)``,
    so a save of what was just read writes the same rows back.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line:
            out.append("")
            continue
        while len(line) > LINE_CHARS:
            cut = line.rfind(" ", 1, LINE_CHARS + 1)
            if cut <= 0:
                cut = LINE_CHARS
            out.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        out.append(line)
    # A trailing blank line is presentation, not content — trimming it is what makes
    # "read, save" a no-op for a note whose text ends in a newline.
    while out and out[-1] == "":
        out.pop()
    return out


def _row_order(row: Any) -> tuple[int, str]:
    address = as_text(getattr(row, "datum_address", ""))
    tail = address.rsplit("-", 1)[-1]
    return (int(tail) if tail.isdigit() else 0, address)


def note_text(document: Any, *, sandbox: str, archetype: Any) -> str:
    """The note's text — covered rows in address order, one line per row.

    A run of title cells within one row is one line's continuation (the run fold's
    meaning), so both the one-cell rows this build writes and a future compacted form
    read identically. Rows the archetype does not cover are skipped, the `entry_rows`
    rule: a stray row renders as nothing rather than as somebody's line.
    """
    lines: list[str] = []
    for row in sorted(getattr(document, "rows", ()) or (), key=_row_order):
        shape = ash.row_shape(row.raw, sandbox=sandbox)
        if archetype is None or not archetype.covers(shape):
            continue
        values = _row_values(ash._row_head(row.raw), namespace=sandbox)
        # No `if v` filter: an all-padding blob IS a value and decodes to the blank line
        # it stores. Filtering falsy magnitudes here would eat every paragraph break.
        lines.append("".join(decode_label(v) for v in values.get("title", ())))
    return "\n".join(lines)


__all__ = [
    "LINE_CHARS",
    "NOTE_ARCHETYPE",
    "NOTE_CHAR_BUDGET",
    "OVEURE_PROVIDERS",
    "note_text",
    "unstorable",
    "wrap_lines",
]
