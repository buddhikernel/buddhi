"""Stage 0: input conditioning (identity pass-through + detection hook)."""

from __future__ import annotations

from dataclasses import replace

from buddhi.reference.naive_pack import mock_raw_items, naive_policy_pack
from buddhi.stage0.conditioning import Item, RawItem, condition


def test_condition_is_identity_passthrough():
    raw = mock_raw_items()
    items = condition(raw)
    assert len(items) == len(raw)  # 1:1
    for r, it in zip(raw, items):
        assert isinstance(it, Item)
        assert it.id == r.id
        assert it.payload == r.payload          # payloads never rewritten
        assert it.source == r.source
        assert it.stakes == r.stakes
        assert it.model_confidence == r.model_confidence
        assert it.changes == r.changes
        assert it.trigger_fired is False         # no pack => no-op trigger


def test_condition_maps_every_field():
    raw = RawItem(
        id="r", payload="hello", source="src", stakes=0.7,
        model_confidence=0.3, changes=("substantive",), meta={"k": "v"},
    )
    items = condition([raw])
    assert len(items) == 1
    item = items[0]
    assert (item.id, item.payload, item.source) == ("r", "hello", "src")
    assert item.stakes == 0.7
    assert item.model_confidence == 0.3
    assert item.changes == ("substantive",)
    assert item.meta == {"k": "v"}


def test_trigger_hook_is_detection_only_and_does_not_rewrite():
    pack = replace(
        naive_policy_pack(),
        stage0_trigger=lambda r: "retention" in r.payload.lower(),
    )
    raw = mock_raw_items()
    items = condition(raw, pack=pack)
    fired = {it.id for it in items if it.trigger_fired}
    assert fired == {"i4-escalate-bypass"}  # the only payload mentioning "retention"
    for r, it in zip(raw, items):
        assert it.payload == r.payload  # detection must not rewrite payloads


def test_with_change_is_immutable_append():
    item = Item(id="i", payload="p")
    once = item.with_change("substantive")
    assert once.changes == ("substantive",)
    assert item.changes == ()  # original untouched (frozen dataclass)
    twice = once.with_change("cosmetic")
    assert twice.changes == ("substantive", "cosmetic")
    assert once.changes == ("substantive",)  # intermediate also untouched


def test_rawitem_and_item_defaults():
    raw = RawItem(id="r", payload="p")
    assert raw.source == "unknown"
    assert raw.stakes == 0.0
    assert raw.model_confidence == 1.0
    assert raw.changes == ()
    assert raw.meta == {}
    assert Item(id="i", payload="p").trigger_fired is False
