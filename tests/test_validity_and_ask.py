"""Step 5: validate_and_ask (validity gate + pre-reasoned 2-4 option ask)."""

from __future__ import annotations

import pytest

from buddhi.decisions.judgment_routing import BusinessQuestion
from buddhi.decisions.validity_and_ask import (
    InvalidAsk,
    Option,
    PreReasonedAsk,
    validate_and_ask,
)
from buddhi.policy import AskPolicy, PolicyPack
from buddhi.reference.naive_pack import naive_policy_pack


def _question(payload: str = "a real payload", stakes: float = 0.5, model_confidence: float = 0.1) -> BusinessQuestion:
    return BusinessQuestion(
        item_id="i", source="rev", stakes=stakes,
        model_confidence=model_confidence, question="how?", payload=payload,
    )


def test_valid_question_yields_pre_reasoned_ask():
    ask = validate_and_ask(_question(), naive_policy_pack())
    assert isinstance(ask, PreReasonedAsk)
    assert ask.is_valid is True
    assert len(ask.options) == 3  # naive pack supplies three phrasings
    assert all(isinstance(o, Option) for o in ask.options)


def test_exactly_one_option_is_starred_at_the_recommended_index():
    ask = validate_and_ask(_question(), naive_policy_pack())
    starred = [i for i, o in enumerate(ask.options) if o.recommended]
    assert starred == [ask.recommended_index]
    assert ask.recommended_index == 0


def test_escalation_confidence_blends_stakes_and_unsureness():
    ask = validate_and_ask(_question(stakes=0.5, model_confidence=0.1), naive_policy_pack())
    # 0.5*stakes + 0.5*(1 - model_confidence) = 0.25 + 0.45
    assert ask.confidence == pytest.approx(0.7)


def test_confidence_is_clamped_to_unit_interval():
    hi = validate_and_ask(_question(stakes=1.0, model_confidence=0.0), naive_policy_pack())
    lo = validate_and_ask(_question(stakes=0.0, model_confidence=1.0), naive_policy_pack())
    assert hi.confidence == pytest.approx(1.0)
    assert lo.confidence == pytest.approx(0.0)


def test_empty_payload_is_rejected_by_naive_validity_rule():
    ask = validate_and_ask(_question(payload="   "), naive_policy_pack())
    assert isinstance(ask, InvalidAsk)
    assert ask.is_valid is False
    assert "validity rule[0]" in ask.reason


def test_default_pack_has_no_validity_rules_so_any_question_is_valid():
    pack = PolicyPack(name="empty", version="1")  # no validity_rules
    ask = validate_and_ask(_question(payload=""), pack)
    assert ask.is_valid is True
    assert len(ask.options) == 2  # default AskPolicy supplies two phrasings


def test_kernel_floors_options_at_two_even_when_pack_asks_for_one():
    pack = PolicyPack(
        name="p", version="1",
        ask=AskPolicy(option_phrasings=("Only one",), min_options=1, max_options=4),
    )
    ask = validate_and_ask(_question(), pack)
    assert len(ask.options) == 2  # padded up to the hard floor


def test_kernel_caps_options_at_four_even_when_pack_asks_for_more():
    pack = PolicyPack(
        name="p", version="1",
        ask=AskPolicy(
            option_phrasings=("A", "B", "C", "D", "E", "F"),
            min_options=2, max_options=10,
        ),
    )
    ask = validate_and_ask(_question(), pack)
    assert len(ask.options) == 4  # capped to the hard ceiling


def test_recommended_index_is_clamped_into_range():
    high = PolicyPack(
        name="p", version="1",
        ask=AskPolicy(option_phrasings=("A", "B"), recommended_index=99),
    )
    ask = validate_and_ask(_question(), high)
    assert ask.recommended_index == len(ask.options) - 1
    assert ask.options[-1].recommended is True


def test_recommended_index_is_clamped_up_to_zero_when_negative():
    # The lower clamp max(recommended_index, 0): a negative index must star option 0,
    # not survive into Python negative indexing (which would star nothing here).
    low = PolicyPack(
        name="p", version="1",
        ask=AskPolicy(option_phrasings=("A", "B"), recommended_index=-5),
    )
    ask = validate_and_ask(_question(), low)
    assert ask.recommended_index == 0
    assert ask.options[0].recommended is True
    starred = [i for i, o in enumerate(ask.options) if o.recommended]
    assert starred == [0]  # exactly one option starred, at index 0


def test_pack_max_options_truncates_before_the_floor_pads():
    # max_options=1 truncates ("A","B","C") down to ("A",) BEFORE the 2-option floor
    # pads, proving the pack's max_options is the binding truncator (not the hard
    # ceiling of 4) and that truncation happens before padding.
    pack = PolicyPack(
        name="p", version="1",
        ask=AskPolicy(option_phrasings=("A", "B", "C"), min_options=2, max_options=1),
    )
    ask = validate_and_ask(_question(), pack)
    assert [o.label for o in ask.options] == ["A", "Option 2"]
    assert len(ask.options) == 2
