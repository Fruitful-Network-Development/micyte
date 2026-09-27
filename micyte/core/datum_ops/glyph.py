"""The restricted-grammar glyph codec — a drawing whose rows ARE the drawing.

A glyph document is not a description of a picture and not a pointer to one. Its rows
decode to one ``d`` attribute and nothing else is consulted, which is the same move
``archetype`` made when a kind stopped being Python and ``viewscope`` made when a layout
stopped being JavaScript. Here a *picture* stops being an asset.

## The grammar, and why it is restricted

One ``M`` per path, then ``A`` commands and nothing else. No ``C``, no ``Q``, no ``Z``, no
second ``M``. That is narrow on purpose: every command the grammar admits has to be
expressible as datum rows of a fixed arity, and a grammar that quietly accepts what it
cannot re-emit is not a grammar — it is a parser with a lossy branch.

Three things are FIXED rather than stored, because the operator fixed them: the arc's
x-axis rotation is always ``0``, the colour is always the host's ``currentColor``, and a
path is never closed. A field nothing writes is a field six readers will disagree about.

## The two abstractions, and why they are new

``((((siu;512:);512:);1:);0)`` is a point in a 512x512 grid — 262,144 positions, **18
bits**. ``(((siu;512:);1:);0)`` is a length — 512 values, **9 bits**.

Both are chains off the layer-0 spatial-incremental-unit rudi (``0-0-4``), read
outside-in as *extents..., then a count, then the ``0`` that makes it referencable*. The
nominal chain beside it multiplies a COUNT — ``niu-baciloid-256-64`` is 64 characters of
8 bits, 512 bits wide — and applying that rule here would make the grid 4,608 bits. It is
18. So in the spatial chain each nesting names **one dimension's extent** and the width is
the sum of their logs. That difference is the whole reason this is "a new datum abstraction
type" rather than a reuse.

Because the grid chain is four deep its babelette sits at ``4-1-N``, and a row referencing
it is therefore layer **5**. That is a derivation, not a choice, and it is why a glyph's
own rows begin at ``5``.

## A length is stored as ``value - 1``

Nine bits address 1..512, not 0..511. The evidence is the operator's own first arc: the row
carries ``rx = 111111111`` (511) and the path it is said to equal begins ``A512 1``. Without
the offset that arc has a radius of zero, and SVG draws a zero-radius arc as a straight
line — so the rectangle would render as a diagonal and nothing would raise.

A POINT is not offset. Its 512 positions are 0..511 and the far corner is 511, which is what
"262,144 positions" means.

## The row shapes

The value_group IS the tuple count (``micyte.core.mss.document_codec``: "the VG number =
tuple count (0 => refs-only)"), so none of these shapes is declared twice — each row lives
at the address its arity requires.

======================================================  ==================================
``5-1-N``  ``[grid_point, <18b>]``                       a path's ``M``
``5-5-N``  ``[length, rx][length, ry][bool, large]``     one ``A`` command
           ``[bool, sweep][grid_point, <18b>]``
``6-0-N``  ``[~, <M row>, <A row>, ...]``                one path: its M, then its A's
``7-1-N``  ``[<6-0-N>, <fill bit>]``                     that path, filled or not
``8-0-1``  ``[~, <7-1-N>, ...]``                         the drawing
``9-1-1``  ``[<8-0-1>, <path count>]``                   the document's top datum
======================================================  ==================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import field_registry as _fr

#: One dimension of the canvas. A point addresses ``EXTENT * EXTENT`` positions.
GRID_EXTENT = 512

#: Bits per stored magnitude. ``GRID_BITS`` is two dimensions of ``LENGTH_BITS``.
LENGTH_BITS = (GRID_EXTENT - 1).bit_length()          # 9
GRID_BITS = LENGTH_BITS * 2                            # 18
BOOL_BITS = 1

#: The viewBox every glyph is drawn in. Stated once, because the renderer and the codec
#: must not disagree about what a coordinate means.
VIEW_BOX = f"0 0 {GRID_EXTENT} {GRID_EXTENT}"

#: The arc parameter the grammar FIXES. Stored nowhere, emitted always.
X_AXIS_ROTATION = 0

#: Row families, by the arity each shape has.
MOVE_FAMILY = "5-1"
ARC_FAMILY = "5-5"
PATH_FAMILY = "6-0"
FILLED_PATH_FAMILY = "7-1"
DRAWING_FAMILY = "8-0"
GLYPH_FAMILY = "9-1"

#: The reference that spells "this row's cell is a local datum, not an abstraction" — the
#: same ``~`` every VG0 row in every anchor carries.
LOCAL = "~"


class GlyphError(ValueError):
    """A glyph is malformed, or a path is outside the restricted grammar."""


# --- magnitudes -------------------------------------------------------------------------

def encode_length(value: int) -> str:
    """A radius or extent, 1..512, stored as ``value - 1`` in nine bits."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise GlyphError(f"a length is a whole number of spatial units, not {value!r}")
    if not 1 <= value <= GRID_EXTENT:
        raise GlyphError(
            f"length {value} is outside 1..{GRID_EXTENT} — nine bits address "
            f"{GRID_EXTENT} values, and a radius of 0 draws as a straight line"
        )
    return format(value - 1, f"0{LENGTH_BITS}b")


def decode_length(bits: str) -> int:
    return _int_of(bits, LENGTH_BITS, "length") + 1


def encode_point(x: int, y: int) -> str:
    """A grid position, each axis 0..511, stored as ``x`` in the HIGH nine bits."""
    for axis, value in (("x", x), ("y", y)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise GlyphError(f"{axis} is a grid position, not {value!r}")
        if not 0 <= value < GRID_EXTENT:
            raise GlyphError(
                f"{axis}={value} is outside 0..{GRID_EXTENT - 1} — the canvas holds "
                f"{GRID_EXTENT * GRID_EXTENT} positions and its far edge is "
                f"{GRID_EXTENT - 1}"
            )
    return format(x, f"0{LENGTH_BITS}b") + format(y, f"0{LENGTH_BITS}b")


def decode_point(bits: str) -> tuple[int, int]:
    _int_of(bits, GRID_BITS, "point")
    return int(bits[:LENGTH_BITS], 2), int(bits[LENGTH_BITS:], 2)


def encode_flag(value: bool) -> str:
    return "1" if value else "0"


def decode_flag(bits: str) -> bool:
    return bool(_int_of(bits, BOOL_BITS, "flag"))


def _int_of(bits: str, width: int, what: str) -> int:
    text = str(bits or "")
    if len(text) != width or set(text) - {"0", "1"}:
        raise GlyphError(
            f"a {what} is {width} bits of binary, not {text!r} ({len(text)} chars)"
        )
    return int(text, 2)


# --- the shapes -------------------------------------------------------------------------

@dataclass(frozen=True)
class Arc:
    """One ``A`` command. ``rx``/``ry`` are 1..512; the endpoint is a grid position."""

    rx: int
    ry: int
    large: bool
    sweep: bool
    x: int
    y: int

    def to_text(self) -> str:
        return (f"A{self.rx} {self.ry} {X_AXIS_ROTATION} "
                f"{int(self.large)} {int(self.sweep)} {self.x} {self.y}")


@dataclass(frozen=True)
class Path:
    """One ``M`` and the arcs that follow it. A path with no arc draws nothing."""

    x: int
    y: int
    arcs: tuple[Arc, ...]
    fill: bool = False

    def to_text(self) -> str:
        return " ".join((f"M{self.x} {self.y}", *(a.to_text() for a in self.arcs)))


@dataclass(frozen=True)
class Glyph:
    """A drawing: one or more paths, in the order they are painted."""

    paths: tuple[Path, ...]

    def to_path_data(self) -> tuple[str, ...]:
        return tuple(p.to_text() for p in self.paths)


# --- the grammar ------------------------------------------------------------------------

_COMMAND = re.compile(r"([A-Za-z])([^A-Za-z]*)")


def parse_path_data(text: str) -> Path:
    """One ``d`` attribute -> a :class:`Path`, or a refusal that names what it saw."""
    found = _COMMAND.findall(str(text or "").strip())
    if not found:
        raise GlyphError("a path needs at least an M")
    letters = [letter for letter, _ in found]
    if letters[0] != "M":
        raise GlyphError(f"a path opens with M, not {letters[0]!r}")
    if letters.count("M") > 1:
        raise GlyphError(
            f"the grammar admits ONE M per path; this one has {letters.count('M')} — "
            "a second M is a second path, and it is written as one"
        )
    stray = sorted({c for c in letters[1:] if c != "A"})
    if stray:
        raise GlyphError(
            f"the grammar admits M and A only; this path also uses {', '.join(stray)}"
        )

    move = _numbers(found[0][1], 2, "M")
    arcs: list[Arc] = []
    for _, body in found[1:]:
        rx, ry, rotation, large, sweep, x, y = _numbers(body, 7, "A")
        if rotation != X_AXIS_ROTATION:
            raise GlyphError(
                f"the grammar fixes the x-axis rotation at {X_AXIS_ROTATION}; "
                f"this arc rotates by {rotation}"
            )
        if large not in (0, 1) or sweep not in (0, 1):
            raise GlyphError(f"an arc's flags are 0 or 1, not {large} and {sweep}")
        # Encoding is the validator: every bound this codec has is stated once, in the
        # encoders, and parsing goes through them rather than restating any of it.
        encode_length(rx), encode_length(ry), encode_point(x, y)
        arcs.append(Arc(rx, ry, bool(large), bool(sweep), x, y))
    encode_point(*move)
    return Path(move[0], move[1], tuple(arcs))


def _numbers(body: str, count: int, command: str) -> tuple[int, ...]:
    parts = [p for p in re.split(r"[\s,]+", body.strip()) if p]
    if len(parts) != count:
        raise GlyphError(
            f"{command} takes {count} numbers, not {len(parts)} ({body.strip()!r})"
        )
    out: list[int] = []
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            raise GlyphError(f"{command}: {part!r} is not a number") from None
        if value != int(value):
            raise GlyphError(
                f"{command}: {part!r} is fractional, and a spatial incremental unit "
                "is the smallest step there is"
            )
        out.append(int(value))
    return tuple(out)


def glyph_from_path_data(paths: object, *, fills: object = ()) -> Glyph:
    """Several ``d`` attributes -> a :class:`Glyph`. ``fills`` is per path, default off."""
    texts = [str(p) for p in (paths if isinstance(paths, (list, tuple)) else [paths])]
    flags = list(fills) if isinstance(fills, (list, tuple)) else [fills]
    if flags and len(flags) != len(texts):
        raise GlyphError(f"{len(texts)} path(s) and {len(flags)} fill flag(s)")
    built: list[Path] = []
    for index, text in enumerate(texts):
        parsed = parse_path_data(text)
        fill = bool(flags[index]) if flags else False
        built.append(Path(parsed.x, parsed.y, parsed.arcs, fill))
    if not built:
        raise GlyphError("a glyph needs at least one path")
    return Glyph(tuple(built))


# --- rows -------------------------------------------------------------------------------

def markers(namespace: str = _fr.GLYPH) -> dict[str, str]:
    """The three markers a glyph row uses, resolved by NAME against the anchor."""
    return {
        "point": _fr.marker(namespace, "grid_point"),
        "length": _fr.marker(namespace, "length"),
        "flag": _fr.marker(namespace, "nominal"),
    }


def rows_of(glyph: Glyph, *, namespace: str = _fr.GLYPH) -> list[list]:
    """A glyph -> its rows, in document order, as ``[address, *cells], [label]`` pairs."""
    mark = markers(namespace)
    rows: list[list] = []
    moves = 0
    arcs = 0
    filled: list[str] = []

    for index, path in enumerate(glyph.paths, start=1):
        moves += 1
        move_addr = f"{MOVE_FAMILY}-{moves}"
        rows.append([[move_addr, mark["point"], encode_point(path.x, path.y)],
                     [f"path-{index}-move"]])
        members = [move_addr]
        for arc in path.arcs:
            arcs += 1
            arc_addr = f"{ARC_FAMILY}-{arcs}"
            rows.append([[arc_addr,
                          mark["length"], encode_length(arc.rx),
                          mark["length"], encode_length(arc.ry),
                          mark["flag"], encode_flag(arc.large),
                          mark["flag"], encode_flag(arc.sweep),
                          mark["point"], encode_point(arc.x, arc.y)],
                         [f"path-{index}-arc-{len(members)}"]])
            members.append(arc_addr)
        path_addr = f"{PATH_FAMILY}-{index}"
        rows.append([[path_addr, LOCAL, *members], [f"path-{index}"]])
        fill_addr = f"{FILLED_PATH_FAMILY}-{index}"
        rows.append([[fill_addr, path_addr, encode_flag(path.fill)],
                     [f"path-{index}-fill"]])
        filled.append(fill_addr)

    drawing = f"{DRAWING_FAMILY}-1"
    rows.append([[drawing, LOCAL, *filled], ["drawing"]])
    rows.append([[f"{GLYPH_FAMILY}-1", drawing, str(len(glyph.paths))], ["glyph"]])
    return rows


def glyph_of(rows: object, *, namespace: str = _fr.GLYPH) -> Glyph:
    """Rows -> the glyph they draw. The inverse of :func:`rows_of`, exactly."""
    mark = markers(namespace)
    head: dict[str, list] = {}
    for row in rows or ():
        cells = _cells(row)
        if cells:
            head[str(cells[0])] = [str(c) for c in cells[1:]]

    top = head.get(f"{GLYPH_FAMILY}-1")
    if not top or len(top) != 2:
        raise GlyphError(f"no {GLYPH_FAMILY}-1 row — a glyph names its own drawing")
    drawing = head.get(top[0])
    if not drawing or drawing[0] != LOCAL:
        raise GlyphError(f"{top[0]} is not a drawing")
    declared = int(top[1]) if str(top[1]).isdigit() else -1
    if declared != len(drawing) - 1:
        raise GlyphError(
            f"{GLYPH_FAMILY}-1 declares {top[1]} path(s) and the drawing holds "
            f"{len(drawing) - 1}"
        )

    paths: list[Path] = []
    for fill_addr in drawing[1:]:
        filled = head.get(fill_addr)
        if not filled or len(filled) != 2:
            raise GlyphError(f"{fill_addr} is not a path-with-fill row")
        members = head.get(filled[0])
        if not members or members[0] != LOCAL:
            raise GlyphError(f"{filled[0]} is not a path")
        move = head.get(members[1]) if len(members) > 1 else None
        if not move or len(move) != 2 or move[0] != mark["point"]:
            raise GlyphError(f"{filled[0]} opens with no M")
        x, y = decode_point(move[1])
        arcs = tuple(_arc_of(head, addr, mark) for addr in members[2:])
        paths.append(Path(x, y, arcs, decode_flag(filled[1])))
    return Glyph(tuple(paths))


def _arc_of(head: dict[str, list], address: str, mark: dict[str, str]) -> Arc:
    cells = head.get(address)
    if not cells or len(cells) != 10:
        raise GlyphError(f"{address} is not an A command (five tuples, ten cells)")
    want = (mark["length"], mark["length"], mark["flag"], mark["flag"], mark["point"])
    got = tuple(cells[0::2])
    if got != want:
        raise GlyphError(f"{address}: markers {got} are not an A command's {want}")
    rx, ry, large, sweep, end = cells[1::2]
    x, y = decode_point(end)
    return Arc(decode_length(rx), decode_length(ry),
               decode_flag(large), decode_flag(sweep), x, y)


def _cells(row: object) -> list:
    """The head of a row, whether it arrives as a store row or as raw nested lists."""
    raw = getattr(row, "raw", row)
    if isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], (list, tuple)):
        return list(raw[0])
    return list(raw) if isinstance(raw, (list, tuple)) else []


__all__ = [
    "ARC_FAMILY", "BOOL_BITS", "DRAWING_FAMILY", "FILLED_PATH_FAMILY", "GLYPH_FAMILY",
    "GRID_BITS", "GRID_EXTENT", "LENGTH_BITS", "LOCAL", "MOVE_FAMILY", "PATH_FAMILY",
    "VIEW_BOX", "X_AXIS_ROTATION",
    "Arc", "Glyph", "GlyphError", "Path",
    "decode_flag", "decode_length", "decode_point",
    "encode_flag", "encode_length", "encode_point",
    "glyph_from_path_data", "glyph_of", "markers", "parse_path_data", "rows_of",
]
