"""Step 7: Aggregate stream budget (graduated ask bar + exclusion lattice).

Consumes: the per-scope interrupt history (via the Store seam, keyed by a *scope
          key*); the pack's hierarchical weighted budget (``BudgetKnobs``:
          ``daily_interrupt_budget`` + ``base`` / ``cap`` / ``high_stakes_threshold``
          + per-scope ``scope_allocations``); the candidate ``PreReasonedAsk``.
Computes: the graduated ask bar for the scope (how confident an escalation must
          be, given how much of *that scope's* budget is already spent) + the
          two-tier exclusion-lattice check.
Emits:    ``AdmitDecision`` (ADMIT or DENY) + updates the scope's budget state via
          the Store.

The budget is a **hierarchical weighted allocation**: interrupt accounting is
partitioned by a scope key that is a path in a tree (root, then ``/``-joined
child segments, arbitrary depth). Each scope's effective ceiling is the minimum
of the weight-scaled ceiling over the scope and all of its ancestors
(``BudgetKnobs.effective_ceiling``), so a parent's ceiling bounds every scope
beneath it. The **graduated ask bar** for a scope rises monotonically with the
most-binding ancestor's saturation. Per scope the naive is a FIXED LINEAR ramp
between ``base`` and ``cap``:

    required_confidence(spent, budget, scope)
        = base + (cap - base) * (spent / max(1, effective_ceiling(scope)))

and the bar a candidate must clear is the MAXIMUM of that ramp over the scope and
its ancestors, evaluated at each ancestor's own accrued spend.

**Conservation.** Each admitted interrupt is accrued against the scope AND every
ancestor up to the root (see ``_record_subtree_spend``), so an ancestor's count
is the total spend of its whole subtree. Once any ancestor reaches its own
ceiling its ramp sits at ``cap``, so every further marginal ask in that subtree
is denied. A parent ceiling bounds the total marginal spend of its subtree, and
siblings cannot collectively spend past their parent's ceiling. (The soft-bar
non-guarantee still applies: a high-stakes or ``>= cap``-confidence ask clears
any bar; see "high-stakes bypass" below and docs/budget.md.)

Under the degenerate single-scope conditions (one scope, no ``/`` path, uniform
weight 1.0, ceiling equal to the root budget) the scope has exactly one ancestor
(itself), ``effective_ceiling`` collapses to ``daily_interrupt_budget``, the
max-over-ancestors is a single term, and this reduces to the prior single
shared-pool bar.

There is a **high-stakes bypass**: an item whose stakes are ``>= high_stakes_threshold``
is admitted even from a saturated budget. The two-tier **exclusion lattice**
(permanent vs. retractable transient, causes never crossing) lives in the Store
and is global to the store. It is NOT scope-partitioned.

The rising required-confidence bar can be read as a shadow-price on the binding
budget constraint: the pacing view from online-allocation theory (cf. Balseiro,
Lu & Mirrokni, *Dual Mirror Descent for Online Allocation Problems*,
arXiv:2002.10421 / 2011.10124). The kernel ships the fixed linear ramp; a learned
or convex bar is a natural pack-level extension and is not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from buddhi.policy import GLOBAL_SCOPE, scope_ancestors

if TYPE_CHECKING:
    from buddhi.decisions.validity_and_ask import PreReasonedAsk
    from buddhi.policy import BudgetKnobs, PolicyPack
    from buddhi.seams.store import Store

ADMIT = "ADMIT"
DENY = "DENY"


def _record_subtree_spend(store: "Store", scope: str) -> None:
    """Account for one admitted interrupt against ``scope`` and every ancestor.

    Spend accrues up the tree so an ancestor's count is the total spend of its
    whole subtree: the accounting that lets a parent ceiling bound its subtree.
    For a flat (degenerate) scope this is a single ``record_interrupt`` call,
    identical to the prior single-pool behavior.
    """
    for ancestor in scope_ancestors(scope):
        store.record_interrupt(ancestor)


def _subtree_bar(spent_by_scope: Callable[[str], int], budget: "BudgetKnobs", scope: str) -> float:
    """The graduated bar a candidate must clear in ``scope``.

    The maximum, over the scope and all of its ancestors, of each one's own
    ``required_confidence`` evaluated at that ancestor's accrued spend. Whichever
    ancestor is closest to its own ceiling sets the bar, so a saturated parent
    raises the bar for every descendant. A single-ancestor (flat) scope reduces
    this to the plain per-scope bar.
    """
    return max(
        required_confidence(spent_by_scope(a), budget, a) for a in scope_ancestors(scope)
    )


@dataclass(frozen=True)
class AdmitDecision:
    outcome: str  # ADMIT | DENY
    required_confidence: float
    reason: str
    pack: str

    @property
    def admitted(self) -> bool:
        return self.outcome == ADMIT


def required_confidence(spent: int, budget: "BudgetKnobs", scope: str = GLOBAL_SCOPE) -> float:
    """The fixed linear ramp for ONE scope: base -> cap in spent / max(1, effective ceiling).

    The denominator is the scope's effective ceiling (the weight-scaled local
    ceiling, taken as the minimum over the scope and its ancestors). This is the
    per-scope ramp; the bar an admission must clear is the maximum of this ramp
    over the scope and its ancestors (see ``_subtree_bar``). For the default scope
    of a degenerate pack the effective ceiling is exactly
    ``daily_interrupt_budget``: the prior single-pool denominator.
    """
    ratio = spent / max(1, budget.effective_ceiling(scope))
    ratio = min(1.0, max(0.0, ratio))
    return budget.base + (budget.cap - budget.base) * ratio


def aggregate_budget(
    ask: "PreReasonedAsk", store: "Store", pack: "PolicyPack", scope: str = GLOBAL_SCOPE
) -> AdmitDecision:
    """Admit or deny a candidate interrupt against ``scope``'s graduated bar + the lattice.

    The bar is the maximum of the per-scope ramp over ``scope`` and all of its
    ancestors (so a saturated ancestor bounds the subtree), and an admit accrues
    against ``scope`` and every ancestor up to the root. With ``scope ==
    GLOBAL_SCOPE`` (or any flat scope) and a degenerate pack the scope has a
    single ancestor and this is identical to the prior single shared-pool
    decision.
    """
    if ask is None:
        raise TypeError("ask cannot be None")
    if store is None:
        raise TypeError("store cannot be None")
    if pack is None:
        raise TypeError("pack cannot be None")

    audit = f"{pack.name}@{pack.version}"
    budget = pack.budget
    source = ask.question.source

    # 1. exclusion lattice: DENY if excluded in EITHER tier (permanent or transient).
    #    The lattice is global to the store, not scope-partitioned.
    if store.is_excluded(source):
        return AdmitDecision(DENY, 0.0, f"source {source!r} excluded", audit)

    # scope is always passed explicitly (GLOBAL_SCOPE by default at call sites).
    # No legacy no-arg adapter compat is needed: this kernel is staging-only with
    # no published external Store implementations; revisit if a real external
    # adapter ships with the old no-arg signature.
    #
    # The bar is the most-binding ancestor's ramp (spend accrues up the tree, so
    # interrupts_today(ancestor) is that ancestor's whole-subtree spend); admits
    # accrue against the scope and every ancestor.
    bar = _subtree_bar(store.interrupts_today, budget, scope)

    # 2. high-stakes bypass: admitted even from a saturated budget.
    if ask.question.stakes >= budget.high_stakes_threshold:
        _record_subtree_spend(store, scope)
        return AdmitDecision(ADMIT, bar, "high-stakes bypass", audit)

    # 3. graduated ask bar.
    if ask.confidence >= bar:
        _record_subtree_spend(store, scope)
        return AdmitDecision(
            ADMIT, bar, f"confidence {ask.confidence:.2f} >= bar {bar:.2f}", audit
        )
    return AdmitDecision(
        DENY, bar, f"confidence {ask.confidence:.2f} < bar {bar:.2f}", audit
    )
