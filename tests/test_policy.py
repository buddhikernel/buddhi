"""Policy-contract invariants for buddhi.policy.

Covers the value objects the kernel reads judgment from:
``EffortTaxonomy`` (rank/clamp/downgrade + construction guards),
``ConvergenceHeuristics`` (the substantive/cosmetic/transient partition),
``JudgmentPolicy`` / ``AskPolicy`` defaults, and ``BudgetKnobs`` validation.
"""

from __future__ import annotations

import pytest

from buddhi.policy import (
    GLOBAL_SCOPE,
    AskPolicy,
    BudgetKnobs,
    ConvergenceHeuristics,
    EffortTaxonomy,
    JudgmentPolicy,
    PolicyPack,
    ScopeAllocation,
)


# --------------------------------------------------------------------------- #
# EffortTaxonomy
# --------------------------------------------------------------------------- #
class TestEffortTaxonomyRank:
    def test_rank_strictly_orders_levels(self):
        tax = EffortTaxonomy()  # ("low", "medium", "high")
        assert tax.rank("low") < tax.rank("medium") < tax.rank("high")
        assert (tax.rank("low"), tax.rank("medium"), tax.rank("high")) == (0, 1, 2)

    def test_rank_matches_declared_order_for_custom_levels(self):
        tax = EffortTaxonomy(levels=("a", "b", "c", "d"), ceiling="d")
        ranks = [tax.rank(lvl) for lvl in ("a", "b", "c", "d")]
        assert ranks == sorted(ranks)
        assert ranks == [0, 1, 2, 3]


class TestEffortTaxonomyClamp:
    def test_clamp_lowers_level_above_ceiling(self):
        tax = EffortTaxonomy()
        assert tax.clamp("high", ceiling="low") == "low"
        assert tax.clamp("high", ceiling="medium") == "medium"

    def test_clamp_leaves_level_below_ceiling_unchanged(self):
        tax = EffortTaxonomy()
        assert tax.clamp("low", ceiling="high") == "low"
        assert tax.clamp("medium", ceiling="high") == "medium"

    def test_clamp_never_exceeds_ceiling_for_any_level(self):
        tax = EffortTaxonomy()
        for level in tax.levels:
            for ceiling in tax.levels:
                result = tax.clamp(level, ceiling=ceiling)
                assert tax.rank(result) <= tax.rank(ceiling)

    def test_clamp_uses_pack_ceiling_when_none_passed(self):
        tax = EffortTaxonomy(ceiling="medium")
        assert tax.clamp("high") == "medium"
        assert tax.clamp("low") == "low"

    def test_clamp_unknown_level_returns_cap(self):
        tax = EffortTaxonomy()
        assert tax.clamp("nonsense", ceiling="medium") == "medium"

    def test_clamp_unknown_ceiling_falls_back_to_pack_ceiling(self):
        tax = EffortTaxonomy(ceiling="high")
        # An out-of-vocabulary ceiling falls back to the pack's own ceiling.
        assert tax.clamp("high", ceiling="bogus") == "high"


class TestEffortTaxonomyDowngrade:
    def test_downgrade_reduces_by_steps(self):
        tax = EffortTaxonomy()
        assert tax.downgrade("high", 1) == "medium"
        assert tax.downgrade("high", 2) == "low"
        assert tax.downgrade("medium", 1) == "low"

    def test_downgrade_floors_at_cheapest(self):
        tax = EffortTaxonomy()
        assert tax.downgrade("high", 5) == "low"
        assert tax.downgrade("low", 1) == "low"

    def test_downgrade_default_step_is_one(self):
        tax = EffortTaxonomy()
        assert tax.downgrade("high") == "medium"

    def test_downgrade_unknown_level_returns_cheapest(self):
        tax = EffortTaxonomy()
        assert tax.downgrade("nonsense") == "low"


class TestEffortTaxonomyConstruction:
    def test_empty_levels_rejected(self):
        with pytest.raises(ValueError):
            EffortTaxonomy(levels=())

    def test_ceiling_must_be_a_level(self):
        with pytest.raises(ValueError):
            EffortTaxonomy(levels=("low", "high"), ceiling="medium")


# --------------------------------------------------------------------------- #
# ConvergenceHeuristics
# --------------------------------------------------------------------------- #
class TestConvergenceHeuristics:
    def test_classifiers_recognise_each_default_kind(self):
        conv = ConvergenceHeuristics()
        assert conv.is_substantive("substantive")
        assert conv.is_cosmetic("cosmetic")
        assert conv.is_cosmetic("polish")
        assert conv.is_transient("transient_failure")

    def test_classifiers_reject_foreign_kinds(self):
        conv = ConvergenceHeuristics()
        assert not conv.is_substantive("cosmetic")
        assert not conv.is_cosmetic("substantive")
        assert not conv.is_transient("substantive")
        assert not conv.is_substantive("unknown")

    def test_partition_has_no_overlap(self):
        conv = ConvergenceHeuristics()
        sub = set(conv.substantive_kinds)
        cos = set(conv.cosmetic_kinds)
        tra = set(conv.transient_kinds)
        assert sub & cos == set()
        assert sub & tra == set()
        assert cos & tra == set()

    def test_partition_no_overlap_for_custom_kinds(self):
        conv = ConvergenceHeuristics(
            substantive_kinds=("feat", "fix"),
            cosmetic_kinds=("style",),
            transient_kinds=("retry",),
        )
        all_kinds = list(conv.substantive_kinds) + list(conv.cosmetic_kinds) + list(conv.transient_kinds)
        assert len(all_kinds) == len(set(all_kinds))


# --------------------------------------------------------------------------- #
# JudgmentPolicy / AskPolicy defaults
# --------------------------------------------------------------------------- #
class TestSimplePolicyDefaults:
    def test_judgment_default_threshold(self):
        assert JudgmentPolicy().business_question_threshold == pytest.approx(0.6)

    def test_ask_default_bounds(self):
        ask = AskPolicy()
        assert ask.min_options == 2
        assert ask.max_options == 4
        assert ask.recommended_index == 0
        assert len(ask.option_phrasings) >= ask.min_options


# --------------------------------------------------------------------------- #
# BudgetKnobs validation
# --------------------------------------------------------------------------- #
class TestBudgetKnobsValidation:
    def test_defaults_are_valid(self):
        knobs = BudgetKnobs()
        assert knobs.base <= knobs.cap
        assert knobs.daily_interrupt_budget >= 1

    def test_cap_below_base_rejected(self):
        with pytest.raises(ValueError):
            BudgetKnobs(base=0.9, cap=0.5)

    def test_daily_budget_below_one_rejected(self):
        with pytest.raises(ValueError):
            BudgetKnobs(daily_interrupt_budget=0)

    @pytest.mark.parametrize("field", ["base", "cap", "high_stakes_threshold"])
    def test_out_of_unit_range_rejected(self, field):
        with pytest.raises(ValueError):
            BudgetKnobs(**{field: 1.5})


# --------------------------------------------------------------------------- #
# PolicyPack assembly
# --------------------------------------------------------------------------- #
class TestPolicyPackDefaults:
    def test_minimal_pack_defaults_to_keep_all_and_always_valid(self):
        pack = PolicyPack(name="t", version="1")
        assert pack.discard_predicates == ()       # keep-all
        assert pack.validity_rules == ()            # every question valid
        assert isinstance(pack.effort_taxonomy, EffortTaxonomy)
        assert isinstance(pack.convergence, ConvergenceHeuristics)
        assert isinstance(pack.budget, BudgetKnobs)
        # default Stage 0 trigger never fires.
        assert pack.stage0_trigger.__name__ == "_no_trigger"


# --------------------------------------------------------------------------- #
# ScopeAllocation: the per-scope weight + ceiling
# --------------------------------------------------------------------------- #
class TestScopeAllocation:
    def test_degenerate_default_is_unit_weight_and_inherited_ceiling(self):
        alloc = ScopeAllocation()
        assert alloc.weight == pytest.approx(1.0)
        assert alloc.ceiling is None  # None => inherit the root ceiling

    def test_non_positive_weight_rejected(self):
        with pytest.raises(ValueError):
            ScopeAllocation(weight=0.0)
        with pytest.raises(ValueError):
            ScopeAllocation(weight=-1.0)

    def test_ceiling_below_one_rejected_when_set(self):
        with pytest.raises(ValueError):
            ScopeAllocation(ceiling=0)

    def test_explicit_values_round_trip(self):
        alloc = ScopeAllocation(weight=0.5, ceiling=2)
        assert (alloc.weight, alloc.ceiling) == (0.5, 2)


# --------------------------------------------------------------------------- #
# BudgetKnobs scoping: the hierarchical weighted allocation surface
# --------------------------------------------------------------------------- #
class TestBudgetKnobsScoping:
    def test_unconfigured_scope_inherits_the_degenerate_defaults(self):
        # The crux of the reduction: with NO scope_allocations, every scope
        # (the global one and any arbitrary key) collapses to the root budget,
        # weight 1.0. This is the single shared pool.
        b = BudgetKnobs(daily_interrupt_budget=4)
        assert b.weight_for(GLOBAL_SCOPE) == pytest.approx(1.0)
        assert b.effective_ceiling(GLOBAL_SCOPE) == 4
        assert b.effective_ceiling("any/unconfigured/subtree") == 4
        assert b.allocation_for("nope") is b.allocation_for(GLOBAL_SCOPE)  # same degenerate object

    def test_explicit_per_scope_ceiling_is_used(self):
        b = BudgetKnobs(
            daily_interrupt_budget=4,
            scope_allocations={"tight": ScopeAllocation(ceiling=1)},
        )
        assert b.effective_ceiling("tight") == 1          # the tight scope's own ceiling
        assert b.effective_ceiling(GLOBAL_SCOPE) == 4     # others still inherit the root

    def test_weight_scales_the_scope_ceiling(self):
        # weight is a LOCAL scalar on the scope's own ceiling (not a shared share).
        b = BudgetKnobs(
            daily_interrupt_budget=4,
            scope_allocations={"half": ScopeAllocation(weight=0.5)},  # ceiling inherits root 4
        )
        assert b.effective_ceiling("half") == 2           # round(0.5 * 4)
        assert b.weight_for("half") == pytest.approx(0.5)

    def test_effective_ceiling_clamped_to_the_root_budget(self):
        # The hierarchical bound: no subtree can exceed the root budget, whether it
        # over-weights or sets a ceiling above root. A parent bounds its subtree.
        b = BudgetKnobs(
            daily_interrupt_budget=3,
            scope_allocations={
                "over_weight": ScopeAllocation(weight=10.0),
                "over_ceiling": ScopeAllocation(ceiling=99),
            },
        )
        assert b.effective_ceiling("over_weight") == 3
        assert b.effective_ceiling("over_ceiling") == 3

    def test_effective_ceiling_floored_at_one(self):
        b = BudgetKnobs(
            daily_interrupt_budget=4,
            scope_allocations={"tiny": ScopeAllocation(weight=0.1, ceiling=1)},  # round(0.1) -> 0
        )
        assert b.effective_ceiling("tiny") == 1           # never below 1

    def test_non_scopeallocation_value_rejected(self):
        with pytest.raises(TypeError):
            BudgetKnobs(scope_allocations={"bad": (1.0, 2)})  # type: ignore[dict-item]
