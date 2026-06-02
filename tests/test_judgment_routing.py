"""Step 4: route_judgment (model-vs-human routing at the threshold)."""

from __future__ import annotations

from buddhi.decisions.judgment_routing import (
    HUMAN,
    MODEL,
    BusinessQuestion,
    JudgmentDecision,
    route_judgment,
)
from buddhi.reference.naive_pack import naive_policy_pack
from buddhi.stage0.conditioning import Item


def _item(model_confidence: float, **kw) -> Item:
    base = dict(id="i", payload="payload-body", source="rev", stakes=0.4)
    base.update(kw)
    return Item(model_confidence=model_confidence, **base)


def test_high_confidence_handled_by_model():
    decision = route_judgment(_item(0.9), naive_policy_pack())
    assert isinstance(decision, JudgmentDecision)
    assert decision.outcome == MODEL
    assert decision.needs_human is False
    assert decision.question is None


def test_low_confidence_routes_to_human_with_business_question():
    decision = route_judgment(_item(0.2), naive_policy_pack())
    assert decision.outcome == HUMAN
    assert decision.needs_human is True
    q = decision.question
    assert isinstance(q, BusinessQuestion)
    assert q.item_id == "i"
    assert q.source == "rev"
    assert q.stakes == 0.4
    assert q.model_confidence == 0.2
    assert q.payload == "payload-body"


def test_threshold_is_inclusive_lower_bound_for_model():
    # confidence exactly at the threshold (0.6) => model handles it (>=).
    decision = route_judgment(_item(0.6), naive_policy_pack())
    assert decision.needs_human is False


def test_just_below_threshold_routes_to_human():
    decision = route_judgment(_item(0.59), naive_policy_pack())
    assert decision.needs_human is True
