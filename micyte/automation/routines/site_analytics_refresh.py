"""``site_analytics_refresh`` — fold each month's site traffic into the instance's books.

Analytics arrive as monthly leaflets in the FND service's own store. They were
consolidated into every instance's `pim/analytics` document on 2026-08-28, which made a
client's numbers theirs; this is what keeps them so, because a back-fill is a moment and
a month is recurring.

**It declares a WRITE and a CALL.** The call is `fnd_service:analytics.read` — the one
read-only operation on the site port — and the write is the analytics document in the
instance's own app sandbox. Declaring both is the request: an operator grants the call and
the write separately, and a routine holding the call alone can count but not record.

**Named for the job, not the client.** `site_analytics_refresh`, never `mln_analytics`.
Which site it reads comes from the port binding, which is a per-client fact and belongs in
per-client configuration — the `handyman_erp` lesson.

**It ships refusing.** No grant exists until somebody writes one, so every line reads
DENIED on a fresh instance. That is the resting state, not a misconfiguration: the whole
point of declaring an unattended writer is that turning it on is a reviewed act.
"""

from __future__ import annotations

from collections.abc import Mapping

from micyte.ports.datum_write_policy import DeclaredWrite
from micyte.ports.external_call_policy import DeclaredCall

from .._contract import RoutineContext, RoutineDecision, RoutineEffect

#: The service token the FND Service extension is granted under. Host-side (`fnd_app`),
#: and `micyte` may not reach there — the boundary that lets MiCyte ship standalone.
#: Pinned by a test that compares the two.
_FND_SERVICE = "fnd_service"

#: Where the months land. The instance's own app sandbox, one document, one row per
#: period — the shape `site_analytics_month` declares.
ANALYTICS_SANDBOX = "pim"
ANALYTICS_DOCUMENT = "analytics"


class SiteAnalyticsRefreshRoutine:
    """Declared, refusable, and driven by hand until an operator grants it.

    `evaluate` deliberately does not read the leaflets. A routine's `evaluate` returns
    EFFECTS the runner may apply; reaching the port needs the host's adapters and the
    client's credential, and this class's contribution is the DECLARATION the runner
    authorizes and the Functions surface reads.

    Stated as a decline with a reason rather than a stub that raises, because a reason is
    what an operator finds in a log — and "nobody has turned this on" is a true one.
    """

    routine_id = "site_analytics_refresh"
    label = "Site analytics refresh"
    summary = (
        "Read this instance's monthly site traffic through the site port and record it "
        "in its own analytics document — one row per period, merged by domain."
    )
    #: The document it would write. `append` because a month is new, never a correction:
    #: a period already recorded is left alone, so a re-run cannot rewrite history.
    writes = (
        DeclaredWrite(document_kind=ANALYTICS_DOCUMENT, action="append",
                      sandbox_id=ANALYTICS_SANDBOX),
    )
    #: The one operation it needs. Not `page.list`, not `article.publish` — a counter has
    #: no business holding a publisher's grant.
    calls = (
        DeclaredCall(service=_FND_SERVICE, operation="analytics.read"),
    )

    def evaluate(self, context: RoutineContext) -> RoutineDecision:
        """Decide which periods are missing, and return one effect that appends them.

        The port read and the datum write both arrive through ``context.resources`` — the
        host wires them, and this module never learns what a leaflet is or where the store
        lives. That is not fastidiousness: `micyte` may not import `fnd_app`, and a routine
        that reached for either directly could not ship in the published package.

        **A period already recorded is left alone.** The comparison is by period key, so a
        month whose numbers were corrected by hand stays corrected; only genuinely new
        months are appended. That is what makes re-running this safe at any cadence, and
        it is why the declared action is `append` and not `replace` — a replace here would
        rewrite the 138MB catalog blob and would silently overwrite a correction.
        """
        source = context.resources.get("site_analytics")
        if source is None:
            return RoutineDecision(
                fired=False,
                reason=(
                    "no site analytics source in this run's resources: the host wires the "
                    "port read and the datum writer, and without them this routine has "
                    "nothing to read and nowhere to put it"
                ),
                effects=(),
            )

        periods = tuple(source.read())
        recorded = frozenset(source.recorded())
        fresh = tuple(
            entry for entry in periods
            if _as_period(entry) and _as_period(entry) not in recorded
        )
        if not fresh:
            return RoutineDecision(
                fired=False,
                reason=(
                    f"nothing new: the port reports {len(periods)} period(s) and all of "
                    "them are already in this instance's records"
                ),
                effects=(),
            )

        names = ", ".join(sorted(_as_period(entry) for entry in fresh))
        return RoutineDecision(
            fired=True,
            reason=f"{len(fresh)} new period(s) from the site port: {names}",
            effects=(
                RoutineEffect(
                    write=self.writes[0].bound_to(context.sandbox_id),
                    description=f"append {len(fresh)} period(s) to {ANALYTICS_DOCUMENT}: {names}",
                    apply=lambda: source.append(fresh),
                ),
            ),
        )


def _as_period(entry: object) -> str:
    """The period key of one port entry, or ``""`` if it has none.

    Tolerant of a missing key rather than raising, because the port is another codebase's
    output: an entry this routine cannot place in time is one it declines to record, and
    an unattended writer that crashes on a malformed row stops recording the good ones too.
    """
    if not isinstance(entry, Mapping):
        return ""
    value = entry.get("period")
    return str(value).strip() if value is not None else ""
