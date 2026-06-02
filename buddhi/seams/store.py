"""Store seam: aggregate budget counters + the two-tier exclusion lattice.

The kernel is **stateless per item** but **stateful per stream**: the interrupt
counters and the source-exclusion lattice live behind this injectable store
(never a file path or process global; in-memory locally, swappable later).

The exclusion lattice is **two-tier**, and causes never cross between tiers:

  * **permanent**   : hard caps; a source that must never interrupt.
  * **transient**   : a source temporarily errored-out; **retractable** (the
                      errored-bucket comeback) so it can return on its own.

No concrete store ships in the kernel. The in-memory reference adapter lives in
``buddhi/reference/naive_pack.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from buddhi.policy import GLOBAL_SCOPE


@runtime_checkable
class Store(Protocol):
    """Per-stream budget + exclusion state, behind an injectable interface.

    Interrupt accounting is **scope-aware** (step 7's hierarchical weighted
    budget): counts are partitioned by a *scope key*: a stream id, a subtree id,
    or any ``/``-joined path in the budget tree. The store stays a plain per-key
    counter; ``aggregate_budget`` is what accrues each admitted interrupt against
    the scope AND every ancestor (so a parent's count is the total spend of its
    whole subtree, which is how a parent ceiling bounds its subtree). A store that
    only ever sees ``GLOBAL_SCOPE`` is the degenerate single-pool case. The
    two-tier exclusion lattice is NOT scope-partitioned: a source exclusion is
    global to the store.
    """

    # --- aggregate interrupt budget (step 7) ---
    def interrupts_today(self, scope: str = GLOBAL_SCOPE) -> int:
        """How many interrupts have been admitted under ``scope`` this window.

        Because the budget decision accrues spend up the tree, for an ancestor
        scope this is the total spend of its whole subtree.
        """
        ...

    def record_interrupt(self, scope: str = GLOBAL_SCOPE) -> None:
        """Account for one admitted interrupt against ``scope`` (one key only).

        The caller (``aggregate_budget``) invokes this once per ancestor to accrue
        spend up the tree; the store itself records exactly the key it is given.
        """
        ...

    # --- two-tier exclusion lattice (step 7) ---
    def is_excluded(self, source: str) -> bool:
        """True if ``source`` is excluded in EITHER tier."""
        ...

    def exclude_permanent(self, source: str) -> None:
        """Add a permanent (non-retractable) exclusion."""
        ...

    def exclude_transient(self, source: str) -> None:
        """Add a transient (retractable) exclusion."""
        ...

    def retract_transient(self, source: str) -> None:
        """Retract a transient exclusion (the errored-bucket comeback).

        Must be a no-op for a permanent exclusion. Causes never cross tiers.
        """
        ...
