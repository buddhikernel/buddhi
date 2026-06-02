"""Hierarchical budget conservation: a parent ceiling bounds its whole subtree.

These tests pin the property that earns the "parent bounds subtree" claim:

  * **effective ceiling is the ancestor minimum**: a scope's ceiling is the
    minimum over the scope and all of its ancestors, so a parent's ceiling is a
    hard upper bound on every scope beneath it (not the root alone);
  * **transitive parent bound**: a child can never spend (through the bar) past
    an *intermediate* ancestor's ceiling, even when its own and the root's
    ceilings are far larger;
  * **sibling-sum conservation**: the combined spend of all children of a parent
    cannot exceed that parent's ceiling, because each admit accrues against the
    parent and once the parent saturates every marginal child ask is denied.

The degenerate single (flat) scope reduces all of this to the prior single-pool
behavior. That reduction is pinned in `test_budget_reduction.py`.

The mechanism: `aggregate_budget` accrues each admitted interrupt against the
scope and every ancestor (`scope_ancestors`), and the bar a candidate must clear
is the maximum of the per-scope ramp over the scope and its ancestors. The
soft-bar non-guarantee (a high-stakes or `>= cap`-confidence ask clears any bar)
is documented in `docs/budget.md`; the conservation here is the bar-gated bound.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from buddhi.closure import subtree_scope
from buddhi.decisions.aggregate_budget import ADMIT, DENY, aggregate_budget
from buddhi.decisions.judgment_routing import BusinessQuestion
from buddhi.decisions.validity_and_ask import validate_and_ask
from buddhi.policy import GLOBAL_SCOPE, BudgetKnobs, ScopeAllocation
from buddhi.reference.naive_pack import InMemoryStore, naive_policy_pack


# A scope tree:  root (GLOBAL_SCOPE) -> "p" -> "c"  (and a sibling "c2" under "p").
PARENT = subtree_scope(GLOBAL_SCOPE, "p")            # __global__/p
CHILD = subtree_scope(PARENT, "c")                   # __global__/p/c
SIBLING = subtree_scope(PARENT, "c2")                # __global__/p/c2


def _ask(stakes: float, model_confidence: float, source: str = "rev"):
    pack = naive_policy_pack()
    q = BusinessQuestion(
        item_id="i", source=source, stakes=stakes,
        model_confidence=model_confidence, question="?", payload="a real payload",
    )
    ask = validate_and_ask(q, pack)
    assert ask.is_valid
    return ask


def _marginal_ask():
    """A bar-gated ask (NOT a high-stakes / >= cap bypass): stakes 0.8 (< the 0.9
    high-stakes threshold), confidence 0.9 (< the 0.95 cap). confidence =
    0.5*0.8 + 0.5*(1 - 0.0) = 0.9."""
    ask = _ask(stakes=0.8, model_confidence=0.0)
    assert ask.confidence == pytest.approx(0.9)
    assert ask.question.stakes < 0.9  # would otherwise bypass
    return ask


def _pack(daily, allocations=None):
    return replace(
        naive_policy_pack(),
        budget=BudgetKnobs(
            daily_interrupt_budget=daily, base=0.5, cap=0.95, high_stakes_threshold=0.9,
            scope_allocations=allocations or {},
        ),
    )


# --------------------------------------------------------------------------- #
# effective_ceiling is the minimum over the scope AND its ancestors
# --------------------------------------------------------------------------- #
class TestEffectiveCeilingAncestorClamp:
    def test_effective_ceiling_is_min_over_scope_and_ancestors(self):
        # root ceiling 10, parent "p" ceiling 2, child "c" ceiling 5.
        budget = _pack(
            10,
            {PARENT: ScopeAllocation(ceiling=2), CHILD: ScopeAllocation(ceiling=5)},
        ).budget
        # the child is bounded by its PARENT (2), not its own ceiling (5) or the root (10).
        assert budget.effective_ceiling(CHILD) == 2
        # the parent is bounded by its own ceiling (2), under the root (10).
        assert budget.effective_ceiling(PARENT) == 2
        # the root is itself.
        assert budget.effective_ceiling(GLOBAL_SCOPE) == 10

    def test_child_inherits_when_only_an_ancestor_is_capped(self):
        # only the parent is capped; the child inherits and is bounded by the parent.
        budget = _pack(10, {PARENT: ScopeAllocation(ceiling=3)}).budget
        assert budget.effective_ceiling(CHILD) == 3       # bounded by parent "p"
        assert budget.effective_ceiling(SIBLING) == 3     # the sibling too

    def test_deeper_ancestor_can_be_the_binding_one(self):
        # parent "p" ceiling 4, child "c" ceiling 2: the tighter scope is the child.
        budget = _pack(10, {PARENT: ScopeAllocation(ceiling=4), CHILD: ScopeAllocation(ceiling=2)}).budget
        assert budget.effective_ceiling(CHILD) == 2       # the child's own ceiling binds


# --------------------------------------------------------------------------- #
# transitive parent bound: a child can't spend past an INTERMEDIATE ancestor
# --------------------------------------------------------------------------- #
class TestTransitiveParentBound:
    def test_child_cannot_spend_past_an_intermediate_ancestor_ceiling(self):
        # root 10, parent "p" capped at 2; the child inherits (own/root ceiling 10).
        # Push marginal asks under the child only: it must saturate at the PARENT's
        # 2, never at 10, proving the bound is the intermediate parent, not the root.
        pack = _pack(10, {PARENT: ScopeAllocation(ceiling=2)})
        store = InMemoryStore()
        admitted = 0
        outcomes = []
        for _ in range(8):
            d = aggregate_budget(_marginal_ask(), store, pack, scope=CHILD)
            outcomes.append(d.outcome)
            admitted += d.outcome == ADMIT
            # the parent's accrued count NEVER exceeds its own ceiling for marginal asks.
            assert store.interrupts_today(PARENT) <= 2

        assert admitted == 2, "the child is bounded by the parent ceiling (2), not the root (10)"
        assert store.interrupts_today(CHILD) == 2
        assert store.interrupts_today(PARENT) == 2          # parent saturated
        assert store.interrupts_today(GLOBAL_SCOPE) == 2    # root accrued the subtree spend
        # once the parent saturates, every further marginal ask is denied.
        assert outcomes[2:] == [DENY] * 6

    def test_root_alone_would_not_have_bounded_it(self):
        # Control: with NO parent cap (only the root 10), the same child admits more
        # than 2, so the bound in the test above genuinely comes from the parent.
        pack = _pack(10)  # no scope_allocations: child inherits the root ceiling 10
        store = InMemoryStore()
        admitted = sum(
            aggregate_budget(_marginal_ask(), store, pack, scope=CHILD).outcome == ADMIT
            for _ in range(8)
        )
        assert admitted > 2


# --------------------------------------------------------------------------- #
# sibling-sum conservation: children collectively bounded by the parent
# --------------------------------------------------------------------------- #
class TestSiblingSumConservation:
    def test_combined_child_spend_cannot_exceed_parent_ceiling(self):
        # parent "p" capped at 2, two children "c" and "c2" (both inherit).
        # Interleave marginal asks across the two siblings: their COMBINED admitted
        # spend cannot exceed the parent ceiling (2), because each admit accrues
        # against "p" and the parent's bar saturates for both children together.
        pack = _pack(10, {PARENT: ScopeAllocation(ceiling=2)})
        store = InMemoryStore()
        scopes = [CHILD, SIBLING, CHILD, SIBLING, CHILD, SIBLING]
        admitted = 0
        for scope in scopes:
            d = aggregate_budget(_marginal_ask(), store, pack, scope=scope)
            admitted += d.outcome == ADMIT
            # never, at any step, does the parent's total exceed its ceiling.
            assert store.interrupts_today(PARENT) <= 2

        assert admitted == 2, "siblings collectively cannot exceed the parent ceiling"
        # the parent's count is exactly the sum of its children's spend.
        assert (
            store.interrupts_today(CHILD) + store.interrupts_today(SIBLING)
            == store.interrupts_today(PARENT)
            == 2
        )
        # a further ask to EITHER child is denied: the parent is saturated for the subtree.
        assert aggregate_budget(_marginal_ask(), store, pack, scope=CHILD).outcome == DENY
        assert aggregate_budget(_marginal_ask(), store, pack, scope=SIBLING).outcome == DENY

    def test_a_sibling_does_not_draw_down_anothers_own_counter(self):
        # Isolation still holds under the parent bound: spend in "c" is recorded
        # under "c", not under "c2": only the shared ancestors accrue both.
        pack = _pack(10, {PARENT: ScopeAllocation(ceiling=2)})
        store = InMemoryStore()
        aggregate_budget(_marginal_ask(), store, pack, scope=CHILD)
        assert store.interrupts_today(CHILD) == 1
        assert store.interrupts_today(SIBLING) == 0   # the sibling's own counter is untouched
        assert store.interrupts_today(PARENT) == 1    # the parent accrued it


# --------------------------------------------------------------------------- #
# the documented soft-bar non-guarantee survives at the subtree level
# --------------------------------------------------------------------------- #
class TestSoftBarNonGuaranteeStillApplies:
    def test_high_stakes_bypass_can_push_a_subtree_past_the_parent_ceiling(self):
        # Conservation is a bar-gated bound, not a hard cap: a high-stakes ask
        # clears any bar and accrues up the tree, so it CAN push past the parent
        # ceiling. This pins the documented non-guarantee (docs/budget.md).
        pack = _pack(10, {PARENT: ScopeAllocation(ceiling=1)})
        store = InMemoryStore()
        store.record_interrupt(CHILD)
        store.record_interrupt(PARENT)  # parent already at its ceiling of 1
        high_stakes = _ask(stakes=0.95, model_confidence=0.5)  # >= high_stakes_threshold
        d = aggregate_budget(high_stakes, store, pack, scope=CHILD)
        assert d.outcome == ADMIT and "high-stakes bypass" in d.reason
        assert store.interrupts_today(PARENT) == 2  # pushed past the parent ceiling of 1
