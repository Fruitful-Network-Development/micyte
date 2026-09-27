"""The routines this build ships.

The register is deliberately empty of SCHEDULED work — see :mod:`micyte.automation`. What
lives here is declared, authorizable, and driven by hand until an operator decides
otherwise. That is not a half-measure: the 2026-07-31 decision was that the first routine
to run unattended is the operator's call, and a routine that exists, declares what it
would do, and waits is exactly what makes that call a decision rather than a discovery.
"""

from .._registry import register
from .email_triage import EmailTriageRoutine
from .site_analytics_refresh import SiteAnalyticsRefreshRoutine

# Self-registered on import, the way a workbench tool is. Registering is not scheduling:
# it puts the routine in the register that `authorize_routine` and the Functions surface
# read, and it ships REFUSED like every other unattended caller.
register(EmailTriageRoutine())
register(SiteAnalyticsRefreshRoutine())

__all__ = ["EmailTriageRoutine", "SiteAnalyticsRefreshRoutine"]
