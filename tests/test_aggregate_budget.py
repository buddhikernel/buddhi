"""Step 7: aggregate_budget + required_confidence (graduated bar + lattice)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from buddhi.decisions.aggregate_budget import (
    ADMIT,
    DENY,
    AdmitDecision,
    aggregate_budget,
    required_confidence,
)
from buddhi.decisions.judgment_routing import BusinessQuestion
from buddhi.decisions.validity_and_ask import validate_and_ask
from buddhi.policy import GLOBAL_SCOPE, BudgetKnobs, ScopeAllocation
from buddhi.reference.naive_pack import InMemoryStore, naive_policy_pack


def _ask(stakes: float, model_confidence: float, source: str = "rev"):
    pack = naive_policy_pack()
    q = BusinessQuestion(
        item_id="i", source=source, stakes=stakes,
        model_confidence=model_confidence, question="?", payload="a real payload",
    )
    ask = validate_and_ask(q, pack)
    assert ask.is_valid  # payload is non-empty, so it must pre-reason
    return ask


# --------------------------------------------------------------------------- #
# required_confidence: the graduated ask bar
# --------------------------------------------------------------------------- #
class TestRequiredConfidence:
    def test_exact_ramp_values_for_the_naive_budget(self):
        budget = naive_policy_pack().budget  # daily=3, base=0.5, cap=0.95
        assert required_confidence(0, budget) == pytest.approx(0.50)
        assert required_confidence(1, budget) == pytest.approx(0.65)
        assert required_confidence(2, budget) == pytest.approx(0.80)
        assert required_confidence(3, budget) == pytest.approx(0.95)

    def test_monotonic_non_decreasing_in_spend(self):
        budget = naive_policy_pack().budget
        values = [required_confidence(spent, budget) for spent in range(0, 12)]
        assert values == sorted(values)

    def test_bounded_between_base_and_cap(self):
        budget = naive_policy_pack().budget
        for spent in range(0, 12):
            bar = required_confidence(spent, budget)
            assert budget.base <= bar <= budget.cap

    def test_saturates_at_cap_beyond_full_budget(self):
        budget = naive_policy_pack().budget
        assert required_confidence(4, budget) == pytest.approx(budget.cap)
        assert required_confidence(50, budget) == pytest.approx(budget.cap)


# --------------------------------------------------------------------------- #
# aggregate_budget: admit / deny
# --------------------------------------------------------------------------- #
class TestAdmitGate:
    def test_admits_when_confidence_clears_the_bar(self):
        store = InMemoryStore()  # spent 0 => bar 0.5
        ask = _ask(stakes=0.5, model_confidence=0.1)  # confidence 0.7
        decision = aggregate_budget(ask, store, naive_policy_pack())
        assert isinstance(decision, AdmitDecision)
        assert decision.outcome == ADMIT
        assert decision.admitted is True
        assert store.interrupts_today() == 1  # admit accounts for the interrupt

    def test_admits_when_confidence_exactly_equals_the_bar(self):
        # spent 0 => bar 0.5; stakes 0.0 + model_confidence 0.0 =>
        # confidence = 0.5*0.0 + 0.5*(1.0 - 0.0) = 0.5 == bar. Pins the INCLUSIVE
        # lower bound (>=): equality must ADMIT, not DENY.
        store = InMemoryStore()
        ask = _ask(stakes=0.0, model_confidence=0.0)  # confidence 0.5 == bar 0.5
        assert ask.confidence == pytest.approx(0.5)
        decision = aggregate_budget(ask, store, naive_policy_pack())
        assert decision.outcome == ADMIT
        assert decision.admitted is True
        assert store.interrupts_today() == 1  # admit at the boundary spends budget

    def test_denies_when_confidence_below_the_bar(self):
        store = InMemoryStore()  # spent 0 => bar 0.5
        ask = _ask(stakes=0.3, model_confidence=0.8)  # confidence 0.25
        decision = aggregate_budget(ask, store, naive_policy_pack())
        assert decision.outcome == DENY
        assert decision.admitted is False
        assert store.interrupts_today() == 0  # deny does not spend budget

    def test_saturated_budget_denies_a_marginal_ask(self):
        store = InMemoryStore()
        for _ in range(3):  # spent 3 => bar at cap 0.95
            store.record_interrupt()
        ask = _ask(stakes=0.5, model_confidence=0.1)  # confidence 0.7 < 0.95
        decision = aggregate_budget(ask, store, naive_policy_pack())
        assert decision.outcome == DENY


class TestExclusionLattice:
    def test_excluded_source_is_denied_before_the_bar(self):
        store = InMemoryStore()
        store.exclude_transient("rev")
        ask = _ask(stakes=0.5, model_confidence=0.1, source="rev")
        decision = aggregate_budget(ask, store, naive_policy_pack())
        assert decision.outcome == DENY
        assert "excluded" in decision.reason
        assert decision.required_confidence == pytest.approx(0.0)
        assert store.interrupts_today() == 0  # excluded asks never spend budget

    def test_permanent_exclusion_also_denies(self):
        store = InMemoryStore()
        store.exclude_permanent("rev")
        decision = aggregate_budget(_ask(0.5, 0.1, source="rev"), store, naive_policy_pack())
        assert decision.outcome == DENY
        assert "excluded" in decision.reason


class TestHighStakesBypass:
    def test_high_stakes_admitted_even_from_saturated_budget(self):
        store = InMemoryStore()
        for _ in range(5):  # well past saturation
            store.record_interrupt()
        ask = _ask(stakes=0.95, model_confidence=0.5)  # stakes >= 0.9 => bypass
        decision = aggregate_budget(ask, store, naive_policy_pack())
        assert decision.outcome == ADMIT
        assert "high-stakes bypass" in decision.reason
        assert store.interrupts_today() == 6  # bypass still accounts for the interrupt

    def test_high_stakes_bypass_still_blocked_by_exclusion(self):
        store = InMemoryStore()
        store.exclude_permanent("rev")
        ask = _ask(stakes=0.95, model_confidence=0.5, source="rev")
        decision = aggregate_budget(ask, store, naive_policy_pack())
        assert decision.outcome == DENY  # exclusion is checked before the bypass


# --------------------------------------------------------------------------- #
# Scope-aware budget: the hierarchical weighted allocation in the decision path
# --------------------------------------------------------------------------- #
def _pack(**budget_kwargs):
    base = dict(daily_interrupt_budget=4, base=0.5, cap=0.95, high_stakes_threshold=0.9)
    base.update(budget_kwargs)
    return replace(naive_policy_pack(), budget=BudgetKnobs(**base))


class TestScopedBudget:
    def test_default_scope_is_the_global_scope(self):
        # Omitting the scope must account under GLOBAL_SCOPE: the bridge that makes
        # every legacy (scope-less) call site the degenerate single-pool case.
        store = InMemoryStore()
        aggregate_budget(_ask(stakes=0.5, model_confidence=0.1), store, _pack())
        assert store.interrupts_today() == 1
        assert store.interrupts_today(GLOBAL_SCOPE) == 1  # same counter

    def test_scope_keyed_accounting_is_independent(self):
        # An admit under scope "A" increments only A; "B" is untouched.
        store = InMemoryStore()
        ask = _ask(stakes=0.5, model_confidence=0.1)  # confidence 0.7 clears the base bar
        d = aggregate_budget(ask, store, _pack(), scope="A")
        assert d.outcome == ADMIT
        assert store.interrupts_today("A") == 1
        assert store.interrupts_today("B") == 0

    def test_per_scope_ceiling_enforcement(self):
        # Same spend, different ceilings: the tight scope's bar is saturated while
        # the loose scope's bar is still low, so an identical marginal ask is denied
        # in the tight scope and admitted in the loose one.
        pack = _pack(scope_allocations={"tight": ScopeAllocation(ceiling=1)})  # loose inherits 4
        store = InMemoryStore()
        store.record_interrupt("tight")   # tight: spent 1 / ceiling 1 => bar at cap 0.95
        store.record_interrupt("loose")   # loose: spent 1 / ceiling 4 => bar ~0.61
        ask = _ask(stakes=0.5, model_confidence=0.1)  # confidence 0.7
        assert aggregate_budget(ask, store, pack, scope="tight").outcome == DENY
        assert aggregate_budget(ask, store, pack, scope="loose").outcome == ADMIT

    def test_per_scope_weight_enforcement(self):
        # weight 0.5 halves the effective ceiling, so the down-weighted scope's bar
        # rises twice as fast: after one spend a marginal ask is denied there but
        # admitted in an unweighted (root) scope at the same spend.
        pack = _pack(scope_allocations={"half": ScopeAllocation(weight=0.5)})  # eff ceiling 2
        store = InMemoryStore()
        store.record_interrupt("half")    # half: spent 1 / eff-ceiling 2 => bar 0.725
        store.record_interrupt("full")    # full: spent 1 / ceiling 4 => bar ~0.61
        ask = _ask(stakes=0.5, model_confidence=0.1)  # confidence 0.7
        assert aggregate_budget(ask, store, pack, scope="half").outcome == DENY
        assert aggregate_budget(ask, store, pack, scope="full").outcome == ADMIT

    def test_required_confidence_uses_the_scope_effective_ceiling(self):
        pack = _pack(scope_allocations={"tight": ScopeAllocation(ceiling=1)})
        budget = pack.budget
        # global scope: ceiling 4 -> graduated ramp; tight scope: ceiling 1 -> jumps to cap at spend 1.
        assert required_confidence(1, budget, GLOBAL_SCOPE) == pytest.approx(0.6125)
        assert required_confidence(1, budget, "tight") == pytest.approx(budget.cap)

    def test_exclusion_is_global_across_scopes(self):
        # The exclusion lattice is global to the store, not scope-partitioned: an
        # excluded source is denied under every scope.
        store = InMemoryStore()
        store.exclude_transient("rev")
        ask = _ask(stakes=0.5, model_confidence=0.1, source="rev")
        assert aggregate_budget(ask, store, _pack(), scope="A").outcome == DENY
        assert aggregate_budget(ask, store, _pack(), scope="B").outcome == DENY
