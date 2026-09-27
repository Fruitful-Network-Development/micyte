"""Workbench-tool registry (Plan v2).

Tools self-register by appending to ``TOOL_REGISTRY`` on import. The
workbench runtime imports this module and looks up tools by
``tool_id`` from ``surface_query.tool``.

The registry is intentionally a dict, not a class — tools are global
singletons keyed by ID. Use :func:`register` to add a tool; use
:func:`all_tools` for the menubar palette listing.
"""

from __future__ import annotations

from typing import Any

from micyte.ports.datum_write_policy import DeclaredWrite

from ._contract import WorkbenchTool

# tool_id -> WorkbenchTool instance.
TOOL_REGISTRY: dict[str, WorkbenchTool] = {}


def register(tool: WorkbenchTool) -> WorkbenchTool:
    """Add a tool to the registry. Returns the tool for fluent use.

    Re-registering the same ``tool_id`` overwrites the previous entry —
    useful for tests but typically a tool module is imported once.

    Refuses an :class:`~micyte.automation.AutomationRoutine`. The two registers
    are the tool taxonomy, and a taxonomy nothing enforces is a naming convention:
    a routine landing here would be offered in the palette, asked for a panel it
    has no method for, and — worse — would skip the write authorization the
    routine runner performs. The mirror refusal lives in
    :func:`micyte.automation.register`.
    """
    if not isinstance(tool, WorkbenchTool):
        raise TypeError(
            f"register() expected a WorkbenchTool, got {type(tool).__name__}"
        )
    if hasattr(tool, "routine_id"):
        raise TypeError(
            f"{getattr(tool, 'routine_id', '?')!r} declares routine_id: a "
            "condition-triggered writer belongs in micyte.automation, whose runner "
            "authorizes its writes. Registering it here would render it instead."
        )
    if hasattr(tool, "channel_id"):
        raise TypeError(
            f"{getattr(tool, 'channel_id', '?')!r} declares channel_id: an "
            "outward-facing session surface belongs in micyte.channels, whose open "
            "routes are read-only by construction. Registering it here would offer "
            "it as a tool against the document in focus."
        )
    TOOL_REGISTRY[tool.tool_id] = tool
    return tool


def get(tool_id: str) -> WorkbenchTool | None:
    """Look up a tool by id, or None when absent."""
    return TOOL_REGISTRY.get(tool_id)


def all_tools() -> list[WorkbenchTool]:
    """Return every registered tool, sorted by tool_id for stability."""
    return [TOOL_REGISTRY[k] for k in sorted(TOOL_REGISTRY)]


def declared_writes(tool_id: str) -> tuple[DeclaredWrite, ...]:
    """Every write ``tool_id`` declares. Empty for a viewer, which is the point.

    Read with ``getattr`` rather than off a Protocol member for the reason
    :mod:`._contract` gives about ``core``: :class:`WorkbenchTool` is
    ``runtime_checkable`` and :func:`register` isinstance-checks it, so declaring a
    data attribute there would un-register every tool that does not carry one.
    """
    tool = TOOL_REGISTRY.get(tool_id)
    if tool is None:
        return ()
    return tuple(getattr(tool, "writes", ()) or ())


def requirements_for(tool_id: str) -> Any:
    """What ``tool_id`` declares it NEEDS, or an empty requirement.

    Read with ``getattr`` for the reason :mod:`._contract` gives about ``core`` and
    ``writes``: this Protocol is ``runtime_checkable`` and :func:`register` isinstance-checks
    it, so declaring a data member there would un-register every tool without one.

    An empty requirement is the honest default. A tool that needs nothing provisioned is the
    normal case, and inventing a requirement for it would make an install ask an operator to
    approve something that does not exist.
    """
    from micyte.ports.tool_package import ToolRequirement

    tool = TOOL_REGISTRY.get(tool_id)
    if tool is None:
        return ToolRequirement()
    return getattr(tool, "requires", None) or ToolRequirement()


def instance_can_use(tool_id: str, *, held_documents: Any, sandbox: str = "") -> bool:
    """Can the instance holding ``held_documents`` actually RUN ``tool_id``?

    ``held_documents is None`` means the store could not be read, and answers True: a failed
    read must not empty the rail. Exposure defaults open for the same reason.

    THE ONE PLACE this is decided. The rail and the tool palette both ask it, and asking it
    twice in two files is how they drift — the rail offering a tool the palette hides is a
    difference no test would see, because each file would agree with itself.

    Three questions, not one:

    * ``documents`` — every one must be held. This is the instance KIND.
    * ``documents_any`` — at least one must be held, when any are declared.
    * ``fields`` — the sandbox's anchor must be able to express what the tool writes. Holding
      the file is not the same as being able to write it: a farm holds ``contacts`` and fails
      every save, because the farm anchor defines no ``email``.

    ``sandbox`` is optional and the field check is SKIPPED without it, for the same reason
    ``held_documents is None`` is: not knowing is not knowing it will not work.
    """
    if held_documents is None:
        return True
    requires = requirements_for(tool_id)
    held = set(held_documents)
    if not {d.name for d in requires.documents} <= held:
        return False
    if requires.documents_any and not any(d.name in held for d in requires.documents_any):
        return False
    token = str(sandbox or "").strip()
    if requires.fields and token:
        from micyte.core.datum_ops import field_registry as fr

        try:
            writable = fr.writable_fields(token)
        except KeyError:
            return True
        if not set(requires.fields) <= writable:
            return False
    return True


def tools_requiring() -> dict[str, Any]:
    """Every tool that declares a requirement, ``tool_id -> ToolRequirement``."""
    out = {}
    for tool in all_tools():
        requirement = requirements_for(tool.tool_id)
        if not requirement.is_empty:
            out[tool.tool_id] = requirement
    return out


def write_capable_tools() -> list[WorkbenchTool]:
    """Every tool that declares at least one write, in :func:`all_tools` order.

    The viewer/editor split, as a fact the code can check rather than a naming
    convention: today it is readable only from the ``_viewer`` / ``_manager``
    filename suffix, and a suffix denies nothing.
    """
    return [tool for tool in all_tools() if getattr(tool, "writes", ())]


def _write_owners() -> dict[str, tuple[str, DeclaredWrite]]:
    """action -> (owning tool_id, its declaration). Built fresh; the register is mutable.

    Two tools declaring the same action is a REGISTRATION ERROR, not something to
    resolve by picking one: the choice would silently decide which grant an operator's
    configuration applies to. An action has one owner, and a second surface that posts
    the same route is simply a caller of it — the route resolves the owner from the
    action, never from whoever posted, so a second caller needs no declaration and
    gains nothing by lacking one.
    """
    owners: dict[str, tuple[str, DeclaredWrite]] = {}
    for tool in all_tools():
        for write in getattr(tool, "writes", ()) or ():
            existing = owners.get(write.action)
            if existing is not None:
                raise ValueError(
                    f"{write.action!r} is declared by both {existing[0]!r} and "
                    f"{tool.tool_id!r}. An action has one owning tool: picking one here "
                    "would decide, invisibly, which grant an operator's config applies to. "
                    "Declare it on the tool that owns the document, and let the other "
                    "surface post the route without declaring it."
                )
            owners[write.action] = (tool.tool_id, write)
    return owners


def declaring_tool(action: str) -> tuple[str, DeclaredWrite] | None:
    """The tool that owns ``action``, or ``None`` when nothing declares it.

    ``None`` must be read as DENY by the caller. An action no tool claims is one
    nobody has said is a write of anything, and the write policy cannot judge a
    request it has no ``document_kind`` for — guessing one would mean measuring the
    request against a grant written about a different document.

    The client never supplies the tool id. If it did, a caller would choose its own
    permission dimension and the ``tool_ids`` grant would be worse than absent.
    """
    return _write_owners().get(str(action or "").strip())


def describe_for_palette() -> list[dict[str, Any]]:
    """Render every registered tool as the palette's eligibility dict.

    The menubar palette uses this when the user hasn't selected a
    datum — show all tools, let the user pick one. When a datum *is*
    selected, the workbench runtime filters by applies_to_archetype /
    applies_to_source_kind.
    """
    return [
        {
            "tool_id": t.tool_id,
            "label": t.label,
            "summary": t.summary,
            "applies_to_archetype": list(t.applies_to_archetype),
            "applies_to_source_kind": list(t.applies_to_source_kind),
        }
        for t in all_tools()
    ]
