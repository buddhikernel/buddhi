"""The reduction theorem: the generalized budget collapses to the shared pool.

The kernel's cognitive budget is now a **hierarchical weighted allocation**: a
budget carries a weight, a scope key, and a per-scope ceiling, and a parent budget
can bound its subtree. This module proves the reduction property that earns the
generalization: under the **degenerate conditions** the generalized model produces
the *identical* admit/deny sequence as the prior single shared-pool behavior.

Reduction conditions (stated plainly):

  * **depth-1**: every admission is accounted under one scope (``GLOBAL_SCOPE``);
    there is no subtree partition.
  * **uniform weights**: every scope's weight is ``1.0`` (the naive pack supplies
    no ``scope_allocations``).
  * **ceiling equal to the root budget**: every scope's effective ceiling equals
    ``daily_interrupt_budget``.

Under those three conditions the hierarchy collapses to a single shared global
pool, and the generalized ``aggregate_budget`` is decision-for-decision identical
to the prior shared-pool implementation (the oracle below). The proof is by
differential testing against an explicit oracle over pseudo-random ask sequences,
plus direct pins on the degenerate defaults.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from buddhi.closure import subtree_scope
from buddhi.decisions.aggregate_budget import aggregate_budget
from buddhi.decisions.judgment_routing import BusinessQuestion
from buddhi.decisions.validity_and_ask import validate_and_ask
from buddhi.policy import GLOBAL_SCOPE, BudgetKnobs
from buddhi.reference.naive_pack import InMemoryStore, naive_policy_pack


# --------------------------------------------------------------------------- #
# The shared-pool oracle: the prior behavior, frozen as the reduction target
# --------------------------------------------------------------------------- #
def _oracle_bar(spent: int, daily: int, base: float, cap: float) -> float:
    """The prior single-pool linear ramp (no scopes): base -> cap in spent/daily."""
    ratio = min(1.0, max(0.0, spent / max(1, daily)))
    return base + (cap - base) * ratio


class _SharedPoolOracle:
    """The prior single shared-pool admission logic: one int counter, one ceiling
    (``daily_interrupt_budget``), the same linear ramp + high-stakes bypass. This is
    exactly what the budget was before the generalization."""

    def __init__(self, budget: BudgetKnobs) -> None:
        self.spent = 0
        self._b = budget

    def admit(self, stakes: float, confidence: float) -> bool:
        bar = _oracle_bar(self.spent, self._b.daily_interrupt_budget, self._b.base, self._b.cap)
        if stakes >= self._b.high_stakes_threshold:
            self.spent += 1
            return True
        if confidence >= bar:
            self.spent += 1
            return True
        return False


def _ask(stakes: float, model_confidence: float):
    pack = naive_policy_pack()
    q = BusinessQuestion(
        item_id="i", source="rev", stakes=stakes,
        model_confidence=model_confidence, question="?", payload="a real payload",
    )
    ask = validate_and_ask(q, pack)
    assert ask.is_valid
    return ask


# A spread of valid degenerate budgets: the reduction must hold for all of them.
_BUDGETS = [
    BudgetKnobs(daily_interrupt_budget=1, base=0.5, cap=0.95, high_stakes_threshold=0.9),
    BudgetKnobs(daily_interrupt_budget=2, base=0.4, cap=0.8, high_stakes_threshold=0.85),
    BudgetKnobs(daily_interrupt_budget=3, base=0.5, cap=0.95, high_stakes_threshold=0.9),
    BudgetKnobs(daily_interrupt_budget=5, base=0.3, cap=0.9, high_stakes_threshold=0.95),
    BudgetKnobs(daily_interrupt_budget=8, base=0.6, cap=0.99, high_stakes_threshold=0.8),
]


# --------------------------------------------------------------------------- #
# Differential property test: generalized path ≡ shared-pool oracle
# --------------------------------------------------------------------------- #
class TestReductionToSharedPool:
    @pytest.mark.parametrize("budget", _BUDGETS)
    @pytest.mark.parametrize("seed", range(12))
    def test_generalized_matches_oracle_step_for_step(self, budget, seed):
        """Depth-1, uniform weights, ceiling = root budget: feed an identical
        pseudo-random ask sequence to the generalized scope-keyed path (all asks
        under GLOBAL_SCOPE, naive degenerate pack) and to the prior shared-pool
        oracle. The admit/deny decisions and the running spend must match at every
        step. The hierarchy has collapsed to one shared global pool."""
        pack = replace(naive_policy_pack(), budget=budget)  # NO scope_allocations => degenerate
        store = InMemoryStore()
        oracle = _SharedPoolOracle(budget)
        rng = random.Random(seed)

        for _ in range(40):
            stakes = rng.random()
            model_confidence = rng.random()
            ask = _ask(stakes, model_confidence)

            generalized = aggregate_budget(ask, store, pack)  # scope defaults to GLOBAL_SCOPE
            expected_admit = oracle.admit(ask.question.stakes, ask.confidence)

            assert generalized.admitted is expected_admit
            # running spend stays in lockstep: the scope-keyed counter equals the oracle's int.
            assert store.interrupts_today() == oracle.spent
            assert store.interrupts_today(GLOBAL_SCOPE) == oracle.spent

    @pytest.mark.parametrize("budget", _BUDGETS)
    @pytest.mark.parametrize("seed", range(12))
    def test_single_partitioned_child_with_root_ceiling_matches_oracle(self, budget, seed):
        """Reduction extension to a depth-1 partition: ONE child scope
        (`subtree_scope(GLOBAL_SCOPE, "only")`), uniform weight, ceiling inherited
        from the root, still reduces to the shared pool. Each admit now accrues
        against the child scope AND its root ancestor, but with a single child the
        two counters move together and the bar is the root bar, so the admit/deny
        sequence and the running spend match the shared-pool oracle step for step.
        This pins that ancestor accrual does not double-count or diverge when the
        tree is degenerate."""
        pack = replace(naive_policy_pack(), budget=budget)  # no scope_allocations => child inherits root
        store = InMemoryStore()
        oracle = _SharedPoolOracle(budget)
        rng = random.Random(seed)
        child = subtree_scope(GLOBAL_SCOPE, "only")

        for _ in range(40):
            ask = _ask(rng.random(), rng.random())
            generalized = aggregate_budget(ask, store, pack, scope=child)
            expected_admit = oracle.admit(ask.question.stakes, ask.confidence)

            assert generalized.admitted is expected_admit
            # the child counter tracks the oracle; the root ancestor mirrors it exactly.
            assert store.interrupts_today(child) == oracle.spent
            assert store.interrupts_today(GLOBAL_SCOPE) == oracle.spent

    @pytest.mark.parametrize("budget", _BUDGETS)
    def test_high_stakes_and_marginal_mix_matches_oracle(self, budget):
        """A hand-built adversarial sequence (saturating spend, then high-stakes
        bypass, then marginal asks) reduces identically; pins the bypass and the
        saturated-bar branches, not just the random middle."""
        pack = replace(naive_policy_pack(), budget=budget)
        store = InMemoryStore()
        oracle = _SharedPoolOracle(budget)

        sequence = (
            [(0.5, 0.1)] * 6          # repeated marginal asks: saturate the pool
            + [(0.99, 0.99)] * 3      # high-stakes bypass from a saturated pool
            + [(0.2, 0.9), (0.0, 0.0)]  # clearly-deny + exact-boundary asks
        )
        for stakes, mc in sequence:
            ask = _ask(stakes, mc)
            generalized = aggregate_budget(ask, store, pack)
            expected = oracle.admit(ask.question.stakes, ask.confidence)
            assert generalized.admitted is expected
            assert store.interrupts_today() == oracle.spent


# --------------------------------------------------------------------------- #
# Direct pins on the degenerate defaults that make the reduction hold
# --------------------------------------------------------------------------- #
class TestDegenerateDefaults:
    def test_every_scope_collapses_to_the_root_budget(self):
        budget = naive_policy_pack().budget  # daily=3, no scope_allocations
        assert budget.weight_for(GLOBAL_SCOPE) == pytest.approx(1.0)
        assert budget.effective_ceiling(GLOBAL_SCOPE) == budget.daily_interrupt_budget
        # an arbitrary, never-configured subtree scope also collapses to the root.
        assert budget.effective_ceiling("fleet/team-a/pr-42") == budget.daily_interrupt_budget

    def test_admission_under_an_arbitrary_scope_equals_global_when_degenerate(self):
        # Depth-1 with one (renamed) scope is still one shared pool: routing the same
        # asks through an arbitrary scope key spends and gates identically to the
        # global scope, because the degenerate ceiling is the same.
        pack = replace(
            naive_policy_pack(),
            budget=BudgetKnobs(daily_interrupt_budget=2, base=0.5, cap=0.95, high_stakes_threshold=0.9),
        )
        store_global, store_named = InMemoryStore(), InMemoryStore()
        for _ in range(5):
            ask = _ask(stakes=0.5, model_confidence=0.1)  # confidence 0.7
            d_global = aggregate_budget(ask, store_global, pack)               # GLOBAL_SCOPE
            d_named = aggregate_budget(ask, store_named, pack, scope="solo")   # one renamed scope
            assert d_global.outcome == d_named.outcome
        assert store_global.interrupts_today() == store_named.interrupts_today("solo")
