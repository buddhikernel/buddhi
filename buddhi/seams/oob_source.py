"""OOB-observation-source seam: the can-observe-OOB declaration (interface only).

The adapter declares whether its substrate can *ever* observe an out-of-band
resolution, so the kernel never blocks convergence waiting for a signal the
substrate cannot produce. This declaration is an adapter contract, not core
kernel; any substrate-specific resolver is supplied by the adapter.

This seam carries ONLY the declaration. No concrete source ships in the kernel;
the reference adapter (which declares "cannot observe") lives in
``buddhi/reference/naive_pack.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OOBSource(Protocol):
    """Declares whether this substrate can ever observe an OOB resolution."""

    def can_observe_oob(self) -> bool:
        ...
