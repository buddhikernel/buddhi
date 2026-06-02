"""Step 2: decide_spend (router pick bound to budget + stream ceiling)."""

from __future__ import annotations

from buddhi.decisions.effort_model import IterationBudget, SpendDecision, decide_spend
from buddhi.policy import EffortTaxonomy, PolicyPack
from buddhi.reference.naive_pack import NaiveRouter, naive_policy_pack
from buddhi.stage0.conditioning import Item


def _item(stakes: float) -> Item:
    return Item(id="x", payload="p", stakes=stakes)


def _budget(rounds_remaining: int = 3) -> IterationBudget:
    return IterationBudget(rounds_remaining=rounds_remaining, max_rounds=3)


def test_high_stakes_routes_to_high_effort_and_pack_model():
    pack, router = naive_policy_pack(), NaiveRouter()
    spend = decide_spend(_item(0.8), pack, router, _budget())
    assert isinstance(spend, SpendDecision)
    assert spend.effort == "high"
    assert spend.model == "naive-large"  # pack model_by_effort["high"]


def test_medium_and_low_stakes_route_proportionally():
    pack, router = naive_policy_pack(), NaiveRouter()
    assert decide_spend(_item(0.5), pack, router, _budget()).effort == "medium"
    assert decide_spend(_item(0.1), pack, router, _budget()).effort == "low"


def test_last_round_downgrades_effort():
    pack, router = naive_policy_pack(), NaiveRouter()
    spend = decide_spend(_item(0.8), pack, router, _budget(rounds_remaining=1))
    assert spend.effort == "medium"  # high downgraded one step on the last round
    assert spend.model == "naive-mid"
    assert "downgraded: last round" in spend.rationale


def test_last_round_does_not_underflow_lowest_effort():
    pack, router = naive_policy_pack(), NaiveRouter()
    spend = decide_spend(_item(0.1), pack, router, _budget(rounds_remaining=1))
    # already "low" (rank 0) => no downgrade applied.
    assert spend.effort == "low"
    assert "downgraded" not in spend.rationale


def test_explicit_ceiling_clamps_below_router_pick():
    pack, router = naive_policy_pack(), NaiveRouter()
    spend = decide_spend(_item(0.8), pack, router, _budget(), ceiling="low")
    assert spend.effort == "low"
    assert spend.model == "naive-small"


def test_rationale_records_router_ceiling_and_router_note():
    pack, router = naive_policy_pack(), NaiveRouter()
    spend = decide_spend(_item(0.8), pack, router, _budget())
    assert "router=high" in spend.rationale
    assert "ceiling=high" in spend.rationale
    assert "stakes-based" in spend.rationale  # NaiveRouter's RouterPick.rationale
    assert spend.pack == "naive@1"


def test_model_falls_back_to_router_pick_when_effort_absent_from_pack_map():
    # When the pack's model_by_effort omits the clamped effort level, decide_spend
    # falls back to the router's recommended model (the documented contract).
    pack = PolicyPack(
        name="sparse", version="1",
        effort_taxonomy=EffortTaxonomy(
            levels=("low", "medium", "high"),
            ceiling="high",
            model_by_effort={"low": "x"},  # "medium"/"high" intentionally absent
        ),
    )
    spend = decide_spend(_item(0.8), pack, NaiveRouter(), _budget())  # router effort "high"
    assert spend.effort == "high"
    assert spend.model == "naive-high"  # falls back to RouterPick.model, not a pack value
