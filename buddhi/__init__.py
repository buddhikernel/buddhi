"""buddhi: a composable controller for allocating a bounded cognitive budget.

The kernel is complete in the structural sense: all **seven decision functions**,
**Stage 0**, and the **closure operator** are present and runnable behind **one**
policy contract (``buddhi.policy.PolicyPack``). Completeness is not the same as a
production implementation: the kernel ships competent **naive references**
(``buddhi.reference``) so every cell runs end-to-end. Each reference is the
simplest correct behavior for its seam. For example, the out-of-band resolution
hook reports ``PENDING`` and Stage 0 conditioning is a 1:1 identity pass-through.

The kernel never imports a pack or an adapter; it exposes five seam interfaces
(``buddhi.seams``) they implement. No ambient state, no substrate coupling, no
hardcoded provider: one runtime-neutral policy source.

The **adapter contract** (the boundary every adapter implements) lives in
``buddhi.adapter``: the ``DecisionItem`` / ``Budget`` / ``PolicyResult`` boundary
types + the four-verb ``Adapter`` Protocol (interface only; it composes the seams
and introduces no new mechanism).

Run the smoke path with ``python -m buddhi`` from the repository root.
"""

from __future__ import annotations

__version__ = "0.1.0"

from buddhi.adapter import Adapter, Budget, DecisionItem, PolicyResult
from buddhi.policy import PolicyPack

__all__ = [
    "PolicyPack",
    "Adapter",
    "DecisionItem",
    "Budget",
    "PolicyResult",
    "__version__",
]
