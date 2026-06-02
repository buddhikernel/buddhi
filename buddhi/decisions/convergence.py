"""Step 3: Has it converged? (stop detector + transient-failure class).

Consumes: the item's history (prior rounds' change-kinds); the pack's
          substantive-vs-cosmetic change definition.
Computes: whether the loop has reached a fixed point for this item.
Emits:    ``ConvergenceDecision`` (CONVERGED or CONTINUE).

A change is **substantive** or **cosmetic**. Only substantive changes reset the
convergence clock; cosmetic changes do not. The **transient-failure class** (a
bounded-retry wrapper around a flaky fix) is **excluded from convergence
accounting**. A transient failure is neither progress nor non-progress; it
simply retries.

Naive stop rule (over the accounted history, transient changes filtered out):
  * empty            -> CONTINUE (nothing acted on yet)
  * last substantive -> CONTINUE (progress made; re-check next round)
  * last cosmetic    -> CONVERGED (only polish remains)

``bounded_retry`` is the transient-failure-class wrapper. It is a plain bounded
loop with **no delay and no backoff**. Delay, backoff, and circuit-breakers are
deliberately out of scope for the kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Tuple, TypeVar

if TYPE_CHECKING:
    from buddhi.policy import PolicyPack
    from buddhi.stage0.conditioning import Item

CONVERGED = "CONVERGED"
CONTINUE = "CONTINUE"

T = TypeVar("T")


@dataclass(frozen=True)
class ConvergenceDecision:
    outcome: str  # CONVERGED | CONTINUE
    reason: str
    pack: str

    @property
    def converged(self) -> bool:
        return self.outcome == CONVERGED


def accounted_changes(item: "Item", pack: "PolicyPack") -> Tuple[str, ...]:
    """The item's change history with the transient-failure class removed."""
    conv = pack.convergence
    return tuple(c for c in item.changes if not conv.is_transient(c))


def has_converged(item: "Item", pack: "PolicyPack") -> ConvergenceDecision:
    """Return CONVERGED/CONTINUE for one item. Pure."""
    audit = f"{pack.name}@{pack.version}"
    conv = pack.convergence
    history = accounted_changes(item, pack)
    if not history:
        return ConvergenceDecision(CONTINUE, "no accounted change yet", audit)
    last = history[-1]
    if conv.is_substantive(last):
        return ConvergenceDecision(CONTINUE, "last change substantive", audit)
    if conv.is_cosmetic(last):
        return ConvergenceDecision(CONVERGED, "only cosmetic change remains", audit)
    # Unknown change-kind: conservatively keep going.
    return ConvergenceDecision(CONTINUE, f"unclassified change '{last}'", audit)


class TransientFailure(Exception):
    """Marker for the transient-failure class (excluded from accounting)."""


def bounded_retry(action: Callable[[], T], pack: "PolicyPack") -> T:
    """Run ``action`` up to ``max_transient_retries + 1`` times.

    Re-raises ``TransientFailure`` only after the bounded attempts are exhausted.
    No delay, no backoff (deliberately out of scope). The retries are the
    transient-failure class and do not count toward convergence.
    """
    attempts = max(1, pack.convergence.max_transient_retries + 1)
    last_exc: TransientFailure | None = None
    for _ in range(attempts):
        try:
            return action()
        except TransientFailure as exc:
            last_exc = exc
    assert last_exc is not None
    raise last_exc
