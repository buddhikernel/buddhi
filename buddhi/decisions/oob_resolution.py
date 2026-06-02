"""Step 6: Resolved out of band? (hook interface).

Consumes: one escalated item; the OOB-source declaration (from the seam); an
          optional adapter-injected resolution hook.
Computes: whether the item was already resolved externally (out of band).
Emits:    ``OOBDecision`` (RESOLVED_OOB => skip; PENDING => still open).

The kernel ships the hook **interface** plus the simplest correct naive, the
same posture as every other seam's reference. It declares the hook type and
consults an injected hook only when the substrate can observe OOB at all; the
kernel ships no concrete hook, so the reference behavior is ``PENDING``. Any
substrate-specific resolver is supplied by an adapter, not the kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from buddhi.seams.oob_source import OOBSource
    from buddhi.stage0.conditioning import Item

RESOLVED_OOB = "RESOLVED_OOB"
PENDING = "PENDING"

# The hook INTERFACE: an adapter may inject ``(item) -> bool`` ("was this item
# resolved out of band?"). The kernel ships NO implementation of this hook.
OOBResolutionHook = Callable[["Item"], bool]


@dataclass(frozen=True)
class OOBDecision:
    outcome: str  # RESOLVED_OOB | PENDING
    reason: str

    @property
    def resolved(self) -> bool:
        return self.outcome == RESOLVED_OOB


def check_oob_resolution(
    item: "Item",
    oob_source: "OOBSource",
    hook: Optional[OOBResolutionHook] = None,
) -> OOBDecision:
    """Consult the OOB-source declaration + an optional injected hook.

    * If the substrate cannot observe OOB, return PENDING immediately so the
      kernel never blocks convergence on a signal that can never arrive.
    * Otherwise, if an adapter injected a resolution hook (the interface),
      delegate to it. The kernel ships no hook, so by default this is PENDING.

    No substrate-specific resolver lives here; that is an adapter's job (see the
    module header).
    """
    if not oob_source.can_observe_oob():
        return OOBDecision(PENDING, "substrate cannot observe OOB")
    if hook is None:
        return OOBDecision(PENDING, "no OOB resolution hook injected")
    return OOBDecision(
        RESOLVED_OOB if bool(hook(item)) else PENDING, "delegated to injected hook"
    )
