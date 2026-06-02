"""The runnable naive reference pack: competent naive fills for the seams + policy.

Sufficient for completeness, not the production method. Lets ``buddhi`` run
end-to-end on its own.
"""

from __future__ import annotations

from buddhi.reference.naive_pack import (
    InMemoryStore,
    NaiveAdapter,
    NaiveRouter,
    NoOOBSource,
    RecordingEscalation,
    mock_raw_items,
    mock_stream,
    mock_streams,
    naive_policy_pack,
)

__all__ = [
    "naive_policy_pack",
    "InMemoryStore",
    "NaiveAdapter",
    "NaiveRouter",
    "RecordingEscalation",
    "NoOOBSource",
    "mock_raw_items",
    "mock_stream",
    "mock_streams",
]
