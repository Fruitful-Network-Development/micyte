"""Browse a SAMRAS address space one level at a time.

`registrar/address_nodes` holds 41,999 named street addresses and could not be drawn. The
viewscope refused it — *"41999 rows — more than a record_line draws (2000)"* — and the
obvious fixes are both wrong:

* **raise the cap** — 42,000 ``<tr>`` in the DOM and a 6 MB payload, to show a tree whose
  first useful question is "what is under `3-2-3-17`?";
* **read the document per expand** — 27 MB parsed into 203 MB of row objects, per click.

Neither is necessary, because an address space is not a document. **A SAMRAS address IS
its path** — ``3-2-3-17-18-1`` sits under ``3-2-3-17-18`` — so the hierarchy is already in
the addresses, and the addresses are already in the name index: 49,044 of them, 1.0 MB,
memoized on the store's mtime. This module is the structure over that map, and a level
query is a dict lookup.

**Merged, not per document, and that is the point.** `address_nodes` names the leaves and
`registrar/administrative` names the cities above them. A tree of `address_nodes` alone
would hang 41,999 street addresses off other street addresses, because nearest-present
-ancestor has nothing else to attach to. One space, every name table that names into it —
which is what :attr:`NameIndex.tables` is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text

from ._node_names import NameIndex

#: Default children returned per level. A level is a browse step, not a page: 500 siblings
#: is already past what anyone reads, and the count is always reported exactly so a
#: truncated level says so rather than looking complete.
MAX_LEVEL_NODES = 500

#: Nodes in the opening view. Small on purpose — this is the payload every open of an
#: oversized name table pays for, and the whole point is that it does not grow with the
#: space. 300 is roughly the registrar down to county level.
OPENING_BUDGET = 300


def sort_key(address: str) -> tuple:
    """Numeric-segment order, so ``3-2-3-17-9`` sorts before ``3-2-3-17-10``."""
    return tuple(int(part) if part.isdigit() else part for part in address.split("-"))


@dataclass(frozen=True)
class AddressSpace:
    """Parent/child structure over every address in one index.

    Built once per index (so once per store write) and asked many times. The build is a
    sort plus one pass with a stack: measured on the live registrar, **49,044 addresses in
    0.2 s**, against 5.5 s and 203 MB to read `address_nodes` even once.
    """

    names: NameIndex
    children: dict[str, list[str]] = field(default_factory=dict)
    depth_of: dict[str, int] = field(default_factory=dict)
    #: Total descendants, not direct children. A node showing "3" that opens onto 900 is
    #: worse than no count at all — the number is what tells an operator whether to open it.
    subtree: dict[str, int] = field(default_factory=dict)

    @property
    def roots(self) -> list[str]:
        return self.children.get("", [])

    def __len__(self) -> int:
        return len(self.depth_of)

    def node(self, address: str) -> dict[str, Any]:
        kids = self.children.get(address, ())
        return {
            "address": address,
            "label": self.names.label(address),
            "named": bool(self.names.name_for(address)),
            "depth": self.depth_of.get(address, 0),
            "children": len(kids),
            "descendants": self.subtree.get(address, 0),
        }

    def adopt(self, parent: str, address: str) -> None:
        """Fold a just-minted child into the structure, as a rebuild would have it.

        Same reason as :meth:`NameIndex.remember`: a mint that adds a street and then a
        house under it needs the second step to see the first, and rebuilding this — 0.2s
        over 49,044 addresses, plus the index read behind it — between two appends of one
        request is the whole cost this module exists to avoid paying.

        The subtree counts of every ancestor go up by one, because that is what they count.
        A count left stale would show a browser "27 addresses" on a street that has 28.
        """
        parent_token, token = as_text(parent), as_text(address)
        if not token or token in self.depth_of:
            return
        self.children.setdefault(parent_token, []).append(token)
        self.children[parent_token].sort(key=sort_key)
        self.depth_of[token] = self.depth_of.get(parent_token, -1) + 1
        self.subtree.setdefault(token, 0)
        walk = parent_token
        while walk:
            self.subtree[walk] = self.subtree.get(walk, 0) + 1
            walk = walk.rsplit("-", 1)[0] if "-" in walk else ""

    def level(self, root: str = "", *, limit: int = MAX_LEVEL_NODES) -> dict[str, Any]:
        """The direct children of ``root`` (or the roots), and what each holds.

        ``root`` must be an address the space actually holds — an unknown one is answered
        with a reason rather than with the roots, because silently drawing the top when
        asked for a branch is the "fell through to the first document" failure the
        viewscope pane was written to end.
        """
        token = as_text(root)
        if token and token not in self.depth_of:
            return {"root": token, "nodes": [], "total": 0,
                    "reason": f"{token} is not an address this space holds"}
        kids = self.children.get(token, [])
        return {
            "root": token,
            "root_label": self.names.label(token) if token else "",
            "root_depth": self.depth_of.get(token, -1) if token else -1,
            "nodes": [self.node(child) for child in kids[:limit]],
            "total": len(kids),
            "truncated": max(0, len(kids) - limit),
        }

    def tree(self, root: str = "", *, budget: int = OPENING_BUDGET) -> dict[str, Any]:
        """An opening view: descend from ``root`` while the node count stays under budget.

        The roots alone are a bad first screen — the registrar's are eight hemisphere
        nodes, seven of them empty and one holding 44,872 descendants. Expanding
        BREADTH-first under a budget instead lands the operator somewhere legible (down to
        counties, here) without ever building a payload proportional to the space.

        Chosen breadth-first and emitted depth-first: which nodes to open is a question
        about levels, and how to draw them is a question about order. A depth-first
        expansion under the same budget would spend it all down one branch.
        """
        token = as_text(root)
        if token and token not in self.depth_of:
            return {"root": token, "nodes": [], "total": 0, "opened": 0,
                    "reason": f"{token} is not an address this space holds"}

        opened: set[str] = {token}
        frontier = [token]
        shown = len(self.children.get(token, ()))
        while frontier and shown < budget:
            parent = frontier.pop(0)
            for child in self.children.get(parent, ()):
                kids = self.children.get(child, ())
                if not kids or shown + len(kids) > budget:
                    continue
                opened.add(child)
                shown += len(kids)
                frontier.append(child)

        nodes: list[dict[str, Any]] = []
        stack = [(child, 0) for child in reversed(self.children.get(token, ()))]
        while stack:
            address, depth = stack.pop()
            node = self.node(address)
            node["depth"] = depth
            # `loaded` is the difference between "no children" and "children not fetched
            # yet". A renderer that could not tell them apart would draw a leaf twist on a
            # county holding 44,000 addresses — or send a request for a leaf's children,
            # which is why a childless node is loaded by definition and not by expansion.
            node["loaded"] = not self.children.get(address) or address in opened
            nodes.append(node)
            if address in opened:
                stack.extend(
                    (child, depth + 1) for child in reversed(self.children.get(address, ()))
                )
        return {
            "root": token,
            "root_label": self.names.label(token) if token else "",
            "path": self.path(token) if token else [],
            "nodes": nodes,
            "total": len(self),
            "opened": len(opened) - 1,
            "roots": len(self.children.get(token, ())),
            "max_depth": max((n["depth"] for n in nodes), default=0),
        }

    def path(self, address: str) -> list[dict[str, Any]]:
        """Every ancestor of ``address`` in the space, outermost first, then itself.

        The breadcrumb a lazy tree needs to open onto a deep node without walking down to
        it, and the answer to "where am I" once the root is no longer the top.
        """
        token = as_text(address)
        if token not in self.depth_of:
            return []
        parts = token.split("-")
        trail = [
            "-".join(parts[:cut])
            for cut in range(1, len(parts) + 1)
            if "-".join(parts[:cut]) in self.depth_of
        ]
        return [self.node(step) for step in trail]


def build_address_space(names: NameIndex, *, key_field: str = "") -> AddressSpace:
    """Fold an index's addresses into a tree.

    ``key_field`` narrows to the tables that key on it — an msn space and an lcl space
    share an index and must not share a tree, since ``1-1-1`` is a legal class in one and
    an employee class in the other. Without it every address in the index is included,
    which is right only when the index holds one space.
    """
    wanted = as_text(key_field)
    if wanted:
        keyed = {table.key_field for table in names.tables}
        if wanted not in keyed:
            return AddressSpace(names=names)
    addresses = sorted(names.addresses(key_field=wanted), key=sort_key)

    children: dict[str, list[str]] = {}
    depth_of: dict[str, int] = {}
    # One pass with an ancestor stack, in sorted order: a node's nearest present ancestor
    # is the deepest entry on the stack that is a prefix of it. Sorted order guarantees
    # every ancestor has already been seen, so this replaces the per-node prefix search
    # `_tree_payload` does — which is O(depth) per node and fine for 4,119 taxonomy nodes,
    # and 49,044 x 11 segments here.
    stack: list[str] = []
    for address in addresses:
        while stack and not address.startswith(stack[-1] + "-"):
            stack.pop()
        parent = stack[-1] if stack else ""
        children.setdefault(parent, []).append(address)
        depth_of[address] = len(stack)
        stack.append(address)

    # Descendant counts, deepest first, so each node adds its children's totals to its own.
    subtree: dict[str, int] = {}
    for address in sorted(addresses, key=lambda a: -depth_of[a]):
        kids = children.get(address, ())
        subtree[address] = len(kids) + sum(subtree.get(child, 0) for child in kids)

    return AddressSpace(names=names, children=children, depth_of=depth_of, subtree=subtree)


def address_space_for(names: NameIndex, *, key_field: str = "") -> AddressSpace:
    """:func:`build_address_space`, memoized ON THE INDEX.

    Not in a module-level dict keyed on ``id(names)``: an index that fell out of its own
    memo would free the id for the next one, and the cached space would then describe a
    store that had since been written to. Hanging it off the index gives it exactly the
    index's lifetime, and the index is already keyed on the store's mtime — one
    invalidation, not two that can disagree.
    """
    token = as_text(key_field)
    hit = names._spaces.get(token)
    if hit is None:
        hit = build_address_space(names, key_field=token)
        names._spaces[token] = hit
    return hit


__all__ = [
    "MAX_LEVEL_NODES",
    "AddressSpace",
    "address_space_for",
    "build_address_space",
    "sort_key",
]
