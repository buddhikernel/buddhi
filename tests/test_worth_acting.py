"""Step 1: worth_acting (the cheap pre-model discard gate)."""

from __future__ import annotations

from buddhi.decisions.worth_acting import DISCARD, KEEP, KeepDecision, worth_acting
from buddhi.policy import PolicyPack
from buddhi.reference.naive_pack import naive_policy_pack
from buddhi.stage0.conditioning import Item


def _item(**kw) -> Item:
    base = dict(id="x", payload="p")
    base.update(kw)
    return Item(**base)


def test_keep_when_no_predicate_matches():
    pack = naive_policy_pack()  # discard predicate keys off meta["out_of_scope"]
    decision = worth_acting(_item(meta={}), pack)
    assert isinstance(decision, KeepDecision)
    assert decision.outcome == KEEP
    assert decision.keep is True


def test_discard_when_predicate_matches():
    pack = naive_policy_pack()
    decision = worth_acting(_item(meta={"out_of_scope": True}), pack)
    assert decision.outcome == DISCARD
    assert decision.keep is False
    assert "predicate[0]" in decision.reason


def test_default_pack_keeps_all():
    # No discard predicates => keep-all, even for an item the naive pack would drop.
    pack = PolicyPack(name="empty", version="1")
    decision = worth_acting(_item(meta={"out_of_scope": True}), pack)
    assert decision.keep is True


def test_first_matching_predicate_wins_and_is_reported():
    never = lambda item: False
    always = lambda item: True
    pack = PolicyPack(name="p", version="9", discard_predicates=(never, always))
    decision = worth_acting(_item(), pack)
    assert decision.keep is False
    assert "predicate[1]" in decision.reason  # index of the matching predicate


def test_audit_string_carries_pack_identity():
    decision = worth_acting(_item(), naive_policy_pack())
    assert decision.pack == "naive@1"
