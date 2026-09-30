"""The class layer: the partition, the drawing it induces, and what it refuses.

The archetype library checks itself three ways because an archetype IS an instance of the
shape it names. A class has no shape, so what it has instead is the PARTITION — every
archetype in exactly one class, asserted in both directions. These are the tests for that,
and for the resolution order it buys.

Every negative here was run against the pre-change tree first and observed to fail; a guard
that passes before and after is asserting today's behaviour, not the change.
"""

from __future__ import annotations

import pytest

from micyte.core.datum_ops import archetype_class as ac
from micyte.core.datum_ops import viewscope as vs

TITLE = "rf.3-1-3"          # `title` in the archetype namespace


def _rows(*specs):
    return [{"datum_address": a, "raw": raw} for a, raw in specs]


def _doc(name, rows, *, role=ac.ROLE_VALUE):
    class _D:
        document_id = f"lv.3-2-3.archetype.{name}." + "0" * 64
        canonical_name = name
        document_metadata = {"role": role}
    d = _D()
    d.rows = [type("R", (), r)() for r in ({"datum_address": x["datum_address"],
                                            "raw": x["raw"]} for x in rows)]
    return d


def _klass(name, *, organizer="", container="", parent="", members=(), slots=()):
    return ac.ArchetypeClass(
        name=name, organizer=organizer, container=container, parent=parent,
        members=tuple(members),
        slots=tuple(ac.SlotSpec(group=g, primitive=p, field=f) for g, p, f in slots),
    )


def _library(*classes):
    docs = []
    for klass in classes:
        rows = ac.build_class_rows(klass)
        docs.append(_doc(ac.class_name(klass.name), rows))
    registry, problems = ac.load_classes(docs)
    return registry, problems


# --- the format round-trips -----------------------------------------------------------


def test_a_class_survives_its_own_round_trip():
    """Writer and reader live in one module so they cannot drift. Prove it, because
    `viewscope`'s mint failed exactly this 13 times out of 13 the first time it ran."""
    original = _klass(
        "profile", organizer="subject", container="slot_grid",
        members=("legal_entity_profile", "ag_profile"),
        slots=(("identity", "node_chip", "msn_id"), ("contact", "field_pair", "email")),
    )
    registry, problems = _library(original)
    assert problems == []
    back = registry.get("profile")
    assert back is not None
    assert back.organizer == "subject"
    assert back.container == "slot_grid"
    assert back.members == ("legal_entity_profile", "ag_profile")
    assert [(s.group, s.primitive, s.field) for s in back.slots] == [
        ("identity", "node_chip", "msn_id"), ("contact", "field_pair", "email")]


def test_the_class_prefix_cannot_collide_with_a_live_archetype():
    """`class_record` is a live ARCHETYPE, so a class called `record` under a `class_`
    prefix would have collided with it on the first write. This is why the prefix is
    `kind_`, and the test exists so nobody 'tidies' it back."""
    assert ac.CLASS_PREFIX == "kind_"
    assert ac.class_name("record") == "kind_record"
    assert ac.class_name("record") != "class_record"
    assert ac.name_of("kind_record") == "record"
    assert ac.name_of("class_record") == ""


# --- the partition, in both directions ------------------------------------------------


def test_an_archetype_in_two_classes_is_reported():
    """A row matching two classes has no class: the binding would resolve by iteration
    order, which is not a denotation. Same rule `ambiguities()` applies one level down."""
    registry, _ = _library(
        _klass("record", organizer="address", container="record_line"),
        _klass("registry", parent="record", members=("record",)),
        _klass("contacts", parent="record", members=("record",)),
    )
    problems = ac.partition_problems(registry, ["record"])
    assert any("claimed by 2 classes" in p for p in problems), problems


def test_an_archetype_no_class_names_is_reported():
    """THE direction that matters. A class naming a missing archetype is loud the first
    time anything reads it; an archetype nothing classes is silent — it just never inherits
    a viewscope, which looks exactly like the orphan state this layer exists to end."""
    registry, _ = _library(
        _klass("record", organizer="address", container="record_line", members=("record",)),
    )
    problems = ac.partition_problems(registry, ["record", "geospatial_polygon"])
    assert any("'geospatial_polygon' belongs to no class" in p for p in problems), problems


def test_a_class_naming_a_missing_archetype_is_reported():
    registry, _ = _library(
        _klass("log", organizer="time", container="record_line", members=("no_such_thing",)),
    )
    problems = ac.partition_problems(registry, ["record"])
    assert any("not an archetype" in p for p in problems), problems


def test_a_parent_cycle_is_reported_and_does_not_hang():
    registry, _ = _library(
        _klass("a", organizer="subject", container="slot_grid", parent="b"),
        _klass("b", parent="a", members=("record",)),
    )
    # The walk stops at the repeat rather than spinning: a malformed library degrades to a
    # short answer, and the defect is REPORTED rather than hung on.
    assert registry.ancestry("a") == ("a", "b")
    problems = ac.partition_problems(registry, ["record"])
    assert any("CYCLE" in p for p in problems), problems


def test_an_unknown_organizer_is_refused_not_passed_through():
    """The organizer selects the container, so one nothing implements would silently draw
    with the fallback and read as a rendering bug three layers away."""
    bad = _klass("weird", organizer="vibes", container="slot_grid", members=("record",))
    doc = _doc(ac.class_name("weird"), ac.build_class_rows(bad))
    klass, problems = ac.load_class(doc)
    assert klass is None
    assert any("unknown organizer" in p for p in problems), problems


def test_a_document_without_the_class_role_is_not_a_class():
    """By declared ROLE, not by sandbox or name — the same rule the archetype library uses,
    so a viewscope document sitting beside a class never reads as one."""
    klass = _klass("profile", organizer="subject", container="slot_grid")
    doc = _doc("kind_profile", ac.build_class_rows(klass), role="viewscope")
    assert ac.load_class(doc) == (None, [])


# --- inheritance ----------------------------------------------------------------------


def test_a_leaf_inherits_organizer_and_container_from_its_root():
    registry, problems = _library(
        _klass("log", organizer="time", container="record_line",
               slots=(("", "field_pair", "utc"),)),
        _klass("job_log", parent="log", members=("job_event",)),
    )
    assert problems == []
    leaf = registry.get("job_log")
    assert leaf.organizer == "time"
    assert leaf.container == "record_line"
    assert registry.organizer_of("job_event") == "time"
    assert registry.lineage_of("job_event") == ("job_log", "log")


def test_the_nearest_class_with_slots_wins_WHOLE():
    """Container and slots travel together. Merging a leaf's slots into an ancestor's was
    the other option and it is worse: two classes would each hold half of one layout and
    the interleaving order would be decided by the walk rather than by anyone."""
    registry, _ = _library(
        _klass("record", organizer="address", container="record_line",
               slots=(("", "node_chip", "msn_id"), ("", "text", "title"))),
        _klass("classification", parent="record", container="tree",
               slots=(("", "node_chip", "lcl_id"),), members=("class_record",)),
    )
    container, specs, declaring = registry.drawing_for("class_record")
    assert declaring == "classification"
    assert container == "tree"
    assert [s.field for s in specs] == ["lcl_id"]


# --- what the class layer BUYS: resolution order ---------------------------------------


def _archetype_viewscope(name, container, fields):
    return vs.Viewscope(
        archetype=name, container=container,
        slots=tuple(vs.Slot(field=f, primitive="text") for f in fields),
    )


def test_an_archetypes_own_viewscope_beats_its_class():
    registry, _ = _library(
        _klass("log", organizer="time", container="record_line",
               slots=(("", "field_pair", "utc"), ("", "text", "title"))),
        _klass("job_log", parent="log", members=("job_event",)),
    )
    own = {"job_event": _archetype_viewscope("job_event", "record_line", ["title"])}
    scope, source = vs.resolve_viewscope("job_event", own, registry)
    assert source == "archetype"
    assert scope is own["job_event"]


def test_a_class_draws_an_archetype_that_has_no_viewscope():
    """The whole point. Before this, four archetypes rendered a sentence where a document
    should be."""
    registry, _ = _library(
        _klass("log", organizer="time", container="record_line",
               slots=(("", "field_pair", "utc"), ("", "text", "title"))),
        _klass("network_log", parent="log", members=("source_entry",)),
    )
    scope, source = vs.resolve_viewscope("source_entry", {}, registry)
    assert source == "class:log"
    assert scope is not None
    assert scope.container == "record_line"
    assert [s.field for s in scope.slots] == ["utc", "title"]


def test_a_class_slot_the_archetype_has_no_field_for_is_DROPPED():
    """A class describes what its members have in common, so it may declare the whole
    vocabulary of its kind. Drawing a field the archetype does not carry would put an empty
    pair on every row of every member that lacks it."""
    registry, _ = _library(
        _klass("profile", organizer="subject", container="slot_grid",
               slots=(("identity", "node_chip", "msn_id"),
                      ("place", "map_ring", "coordinate"),
                      ("contact", "field_pair", "email"))),
        _klass("contacts", parent="profile", members=("natural_entity_profile",)),
    )
    scope, _source = vs.resolve_viewscope(
        "natural_entity_profile", {}, registry, declared_fields=("msn_id", "email"))
    assert [s.field for s in scope.slots] == ["msn_id", "email"]
    assert "coordinate" not in [s.field for s in scope.slots]


def test_no_class_and_no_viewscope_still_resolves_to_nothing():
    """Absence must stay legible. The caller says "no viewscope, and no class draws it
    either" — it does not invent a grid."""
    registry, _ = _library(_klass("log", organizer="time", container="record_line"))
    assert vs.resolve_viewscope("orphan", {}, registry) == (None, "")
    assert vs.resolve_viewscope("orphan", {}, None) == (None, "")


def test_a_class_slot_naming_an_unimplemented_primitive_is_dropped_not_drawn():
    """`load_viewscope` refuses an unknown primitive with a reason; the class path must not
    be the way one gets in through the back door."""
    registry, _ = _library(
        _klass("log", organizer="time", container="record_line",
               slots=(("", "hologram", "utc"), ("", "text", "title"))),
        _klass("job_log", parent="log", members=("job_event",)),
    )
    scope, _ = vs.resolve_viewscope("job_event", {}, registry)
    assert [s.field for s in scope.slots] == ["title"]


@pytest.mark.parametrize("organizer,container", sorted(ac.CONTAINER_FOR_ORGANIZER.items()))
def test_every_organizer_maps_to_a_container_the_renderer_implements(organizer, container):
    assert organizer in ac.ORGANIZERS
    assert container in vs.CONTAINERS


# --- the declarations must not drift apart --------------------------------------------


#: Every script that mints an archetype, and the attribute each states its names in.
#:
#: THREE, not one. This read `mint_archetype_sandbox` alone and therefore checked a
#: SUBSET while reading as complete: `svg_glyph` (minted by `mint_glyph_archetypes`) and
#: `subscription` (by `mint_subscription_archetype`) were invisible to it, went unclassed,
#: and the live `mint_class_library` refused to write — the partition was broken in the
#: store for as long as both had existed, and the guard whose whole job is to say so
#: passed every run. A script minting a FOURTH archetype must be added here.
_ARCHETYPE_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("scripts", "mint_archetype_sandbox", "ARCHETYPES"),
    ("scripts", "mint_glyph_archetypes", "ARCHETYPE"),
    ("fnd_app/scripts", "mint_subscription_archetype", "ARCHETYPE_NAME"),
)


def _load(rel_dir: str, name: str):
    import importlib.util
    import pathlib
    import sys

    root = pathlib.Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(name, root / rel_dir / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: @dataclass resolves its annotations through
    # sys.modules[cls.__module__], so a module that is not there yet raises
    # AttributeError on None rather than anything that names the real problem.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _declared_archetype_names() -> list[str]:
    """Every archetype name any in-repo mint script declares.

    An attribute may hold a list of archetype objects or a single name string; both
    shapes appear in the scripts as written, and normalising here beats making three
    scripts agree on a shape they have no other reason to share.
    """
    names: list[str] = []
    for rel_dir, module_name, attribute in _ARCHETYPE_SOURCES:
        value = getattr(_load(rel_dir, module_name), attribute)
        if isinstance(value, str):
            names.append(value)
            continue
        names.extend(getattr(item, "name", item) for item in value)
    return names


def _declared():
    """The in-repo declarations: the archetypes, and the classes over them.

    Read from the mint scripts rather than from the live store on purpose. This is the
    guard that fires in CI when somebody ADDS an archetype and does not class it — which is
    the silent failure the partition exists to catch, and it must be caught before the mint
    runs, not by an operator noticing a document renders nothing.
    """
    return _load("scripts", "mint_archetype_sandbox"), _load("scripts", "mint_class_library")


def test_every_declared_archetype_is_classed_exactly_once():
    _archetypes_mod, classes_mod = _declared()
    names = _declared_archetype_names()

    registry, problems = _library(
        *[
            _klass(k.name, organizer=k.organizer, container=k.container, parent=k.parent,
                   members=k.members, slots=k.slots)
            for k in classes_mod.CLASSES
        ]
    )
    assert problems == [], problems
    assert ac.partition_problems(registry, names) == []


def test_every_archetype_is_drawn_by_its_own_viewscope_or_by_its_class():
    """No archetype may render "no viewscope, and no class draws it either". That sentence
    is what four archetypes showed an operator before the class layer, and the number it is
    allowed to be is zero."""
    archetypes_mod, classes_mod = _declared()
    registry, _ = _library(
        *[
            _klass(k.name, organizer=k.organizer, container=k.container, parent=k.parent,
                   members=k.members, slots=k.slots)
            for k in classes_mod.CLASSES
        ]
    )
    own = set(archetypes_mod.VIEWSCOPES)
    undrawn = []
    for archetype in archetypes_mod.ARCHETYPES:
        if archetype.name in own:
            continue
        fields = tuple(s.name for s in archetype.slots)
        scope, _source = vs.resolve_viewscope(
            archetype.name, {}, registry, declared_fields=fields)
        if scope is None:
            undrawn.append(archetype.name)
    assert undrawn == [], f"nothing draws: {undrawn}"


def test_every_archetype_the_calendars_requirement_names_classes_under_log():
    """`ANY_LOG` names DOCUMENTS, and each entry declares the archetype its rows will be.
    An entry naming an archetype that is not a log would put the general calendar on
    instances with nothing to draw — the defect `documents_any` was added to fix, re-entered
    through the data instead of through the absence of it.

    Structural, and store-free: it reads the same in-repo mint declarations the partition
    check does, so it runs on a checkout with no deploy tree beside it.
    """
    from micyte.tools._requirements import ANY_LOG

    _archetypes_mod, classes_mod = _declared()
    registry, problems = _library(
        *[
            _klass(k.name, organizer=k.organizer, container=k.container, parent=k.parent,
                   members=k.members, slots=k.slots)
            for k in classes_mod.CLASSES
        ]
    )
    assert problems == [], problems
    assert ANY_LOG.documents_any, "ANY_LOG declares nothing — the calendar's gate is inert"
    for requirement in ANY_LOG.documents_any:
        lineage = registry.lineage_of(requirement.archetype)
        assert lineage, f"{requirement.archetype!r} ({requirement.name}) is classed by nothing"
        assert "log" in lineage, (
            f"{requirement.name} declares {requirement.archetype!r}, whose lineage is "
            f"{lineage} — not a log, so the calendar would be offered wherever it is held"
        )


# --- a job DOCUMENT draws every field it declares --------------------------------------
#
# `job` and `job_service` landed additively (TASK-2026-08-31-002) with no VIEWSCOPES entry
# between them, which is not the neutral "no rendered form yet" state the mapping's own
# docstring describes: both ARE classed, so both resolved through the class layer, and
# `resolve_viewscope` drops a declared field the class's slot template does not name.
# `job_service` lost `price` that way — the per-service amount the multi-service job
# document exists to hold — so a job's services would have drawn their trades and no money
# at all. These are the guards for the entries that fixed it.


def _viewscope_as_minted(module, archetype: str) -> vs.Viewscope:
    """A ``VIEWSCOPES`` entry as the mint builds it: same defaulting, same optional label.

    Rebuilt here rather than imported because the mint constructs it inline in ``main()``,
    behind a ``--db`` this test has no store for. These four lines are the whole of that
    construction, and the mint's own round-trip check is what says if they drift.
    """
    container, specs = module.VIEWSCOPES[archetype]
    return vs.Viewscope(
        archetype=archetype,
        container=container,
        slots=tuple(
            vs.Slot(field=spec[2], primitive=spec[1] or vs.default_primitive(spec[2]),
                    group=spec[0], label=(spec[3] if len(spec) > 3 else ""))
            for spec in specs
        ),
    )


def _class_registry(classes_mod):
    registry, problems = _library(
        *[
            _klass(k.name, organizer=k.organizer, container=k.container, parent=k.parent,
                   members=k.members, slots=k.slots)
            for k in classes_mod.CLASSES
        ]
    )
    assert problems == [], problems
    return registry


def _archetype_fields(archetypes_mod, name: str) -> tuple[str, ...]:
    declared = next(a for a in archetypes_mod.ARCHETYPES if a.name == name)
    return tuple(s.name for s in declared.slots)


@pytest.mark.parametrize("archetype,container", [
    # ONE job described, so a grid; its services are a list, so lines. The same split
    # `job_profile` and `job_log` make one level up, and the reason `job_event` next door
    # is a record_line while this is not.
    ("job", "slot_grid"),
    ("job_service", "record_line"),
])
def test_a_job_document_is_drawn_by_its_own_viewscope(archetype, container):
    archetypes_mod, classes_mod = _declared()
    assert archetype in archetypes_mod.VIEWSCOPES, (
        f"{archetype} has no VIEWSCOPES entry, so it falls through to its class"
    )
    own = {archetype: _viewscope_as_minted(archetypes_mod, archetype)}
    fields = _archetype_fields(archetypes_mod, archetype)
    scope, source = vs.resolve_viewscope(
        archetype, own, _class_registry(classes_mod), declared_fields=fields)
    assert source == "archetype", (
        f"{archetype} resolved through {source!r}; a class layout draws only what its "
        f"members have in common and drops the rest"
    )
    assert scope.container == container
    drawn = [s.field for s in scope.slots]
    assert len(drawn) == len(set(drawn)), f"{archetype} draws a field twice: {drawn}"
    assert set(drawn) == set(fields), (
        f"{archetype} declares {sorted(fields)} and draws {sorted(drawn)}"
    )


def test_a_services_price_is_drawn():
    """THE field this document model exists to hold, and the one the class layer dropped.

    Named on its own because a set comparison passing is not the same as an operator
    seeing a per-service amount: assert the slot, and that its primitive is one that
    renders a VALUE rather than an address.
    """
    archetypes_mod, classes_mod = _declared()
    own = {"job_service": _viewscope_as_minted(archetypes_mod, "job_service")}
    scope, source = vs.resolve_viewscope(
        "job_service", own, _class_registry(classes_mod),
        declared_fields=_archetype_fields(archetypes_mod, "job_service"))
    assert source == "archetype"
    price = next((s for s in scope.slots if s.field == "price"), None)
    assert price is not None, [s.field for s in scope.slots]
    assert price.primitive == "field_pair"


@pytest.mark.parametrize("archetype,dropped", [
    ("job", {"price", "project_ref", "status_ref", "lead_ref"}),
    ("job_service", {"price"}),
])
def test_without_its_own_viewscope_a_job_documents_class_drops_fields(archetype, dropped):
    """The PREMISE the two entries exist for, pinned so it cannot quietly stop being true.

    Measured, not reasoned: `job` classes under `job_profile` -> `profile`, whose
    `_PROFILE_SLOTS` names four of its eight fields; `job_service` under `record`, whose
    `_RECORD_SLOTS` names two of its three. If a later change to those templates makes the
    class layer sufficient, this is the test that fails — and the honest answer then is to
    re-aim it, not to delete the viewscopes it justifies.
    """
    archetypes_mod, classes_mod = _declared()
    fields = _archetype_fields(archetypes_mod, archetype)
    scope, source = vs.resolve_viewscope(
        archetype, {}, _class_registry(classes_mod), declared_fields=fields)
    assert source.startswith("class:"), source
    assert set(fields) - {s.field for s in scope.slots} == dropped
