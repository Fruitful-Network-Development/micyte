"""Phase 18 — Raw analytics event log.

The capture-everything event store is the operator's single source
of factual evidence about website visitors. Insights (visitor
sequences, sessions, path analysis, bot filtering, geo-jump
suspicion) are NEVER stored alongside the raw events — they are
computed on demand from this log via :mod:`derivations`.

See the operator brief in ``/home/admin/.claude/plans/`` for the
full schema rationale + the bullet-point derived operations this
package implements.
"""

from __future__ import annotations

from .bot_detection import classify_user_agent
from .event_schema import (
    CLOCK_SKEW_TOLERANCE_MS,
    COLLECTOR_VERSION,
    EVENT_SCHEMA,
    KNOWN_EVENT_TYPES,
    REQUIRED_EVENT_FIELDS,
    RawEvent,
    coarse_ip_prefix,
    compute_quality_flags,
    salted_hash,
)

__all__ = [
    "CLOCK_SKEW_TOLERANCE_MS",
    "COLLECTOR_VERSION",
    "EVENT_SCHEMA",
    "KNOWN_EVENT_TYPES",
    "REQUIRED_EVENT_FIELDS",
    "RawEvent",
    "classify_user_agent",
    "coarse_ip_prefix",
    "compute_quality_flags",
    "salted_hash",
]
