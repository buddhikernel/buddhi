"""The runnable naive reference pack: seam adapters, policy, and mock data."""

from __future__ import annotations

import pytest

from buddhi.closure import Stream
from buddhi.policy import GLOBAL_SCOPE, PolicyPack
from buddhi.reference.naive_pack import (
    InMemoryStore,
    NaiveRouter,
    NoOOBSource,
    RecordingEscalation,
    mock_raw_items,
    mock_stream,
    mock_streams,
    naive_policy_pack,
)
from buddhi.seams.router import RouterPick
from buddhi.stage0.conditioning import Item


# --------------------------------------------------------------------------- #
# InMemoryStore: counters + two-tier exclusion lattice
# --------------------------------------------------------------------------- #
class TestInMemoryStore:
    def test_interrupt_counter_starts_zero_and_increments(self):
        store = InMemoryStore()
        assert store.interrupts_today() == 0
        store.record_interrupt()
        store.record_interrupt()
        assert store.interrupts_today() == 2

    def test_default_counter_is_the_global_scope(self):
        # The scope-less calls and the explicit GLOBAL_SCOPE calls hit one counter,
        # so the degenerate single-pool behavior is preserved exactly.
        store = InMemoryStore()
        store.record_interrupt()
        assert store.interrupts_today(GLOBAL_SCOPE) == 1
        store.record_interrupt(GLOBAL_SCOPE)
        assert store.interrupts_today() == 2

    def test_counters_are_partitioned_by_scope(self):
        store = InMemoryStore()
        store.record_interrupt("subtree-a")
        store.record_interrupt("subtree-a")
        store.record_interrupt("subtree-b")
        assert store.interrupts_today("subtree-a") == 2
        assert store.interrupts_today("subtree-b") == 1
        assert store.interrupts_today("never-seen") == 0
        assert store.interrupts_today() == 0  # global scope untouched by subtree spend

    def test_permanent_exclusion(self):
        store = InMemoryStore()
        assert store.is_excluded("p") is False
        store.exclude_permanent("p")
        assert store.is_excluded("p") is True

    def test_transient_exclusion_toggles(self):
        store = InMemoryStore()
        store.exclude_transient("t")
        assert store.is_excluded("t") is True
        store.retract_transient("t")
        assert store.is_excluded("t") is False

    def test_transient_retraction_never_crosses_into_permanent(self):
        store = InMemoryStore()
        store.exclude_permanent("p")
        store.retract_transient("p")  # no-op on the permanent tier
        assert store.is_excluded("p") is True

    def test_retracting_unknown_source_is_safe(self):
        InMemoryStore().retract_transient("never-seen")  # must not raise


# --------------------------------------------------------------------------- #
# NaiveRouter: stakes-bracketed effort
# --------------------------------------------------------------------------- #
class TestNaiveRouter:
    @pytest.mark.parametrize(
        "stakes,effort",
        [(0.95, "high"), (0.7, "high"), (0.69, "medium"), (0.4, "medium"), (0.39, "low"), (0.0, "low")],
    )
    def test_effort_brackets(self, stakes, effort):
        pick = NaiveRouter().recommend(Item(id="i", payload="p", stakes=stakes))
        assert isinstance(pick, RouterPick)
        assert pick.effort == effort

    def test_pick_carries_model_and_rationale(self):
        pick = NaiveRouter().recommend(Item(id="i", payload="p", stakes=0.8))
        assert pick.model == "naive-high"
        assert pick.rationale == "stakes-based"


# --------------------------------------------------------------------------- #
# RecordingEscalation + NoOOBSource
# --------------------------------------------------------------------------- #
def test_recording_escalation_records_delivered_asks():
    escalation = RecordingEscalation()
    assert escalation.delivered == []
    sentinel = object()
    escalation.deliver(sentinel)
    assert escalation.delivered == [sentinel]


def test_no_oob_source_cannot_observe():
    assert NoOOBSource().can_observe_oob() is False


# --------------------------------------------------------------------------- #
# naive_policy_pack + mock data
# --------------------------------------------------------------------------- #
class TestNaivePolicyPack:
    def test_shape(self):
        pack = naive_policy_pack()
        assert isinstance(pack, PolicyPack)
        assert (pack.name, pack.version) == ("naive", "1")
        assert len(pack.discard_predicates) == 1
        assert len(pack.validity_rules) == 1
        assert pack.judgment.business_question_threshold == pytest.approx(0.6)
        assert pack.budget.daily_interrupt_budget == 3
        assert pack.effort_taxonomy.model_by_effort["high"] == "naive-large"


class TestMockData:
    def test_mock_raw_items_ids(self):
        ids = [r.id for r in mock_raw_items()]
        assert ids == [
            "i1-discard", "i2-converged", "i3-model", "i4-escalate-bypass",
            "i5-escalate-conf", "i6-deny-marginal", "i7-invalid", "i8-deny-excluded",
        ]

    def test_mock_stream_wraps_eight_conditioned_items(self):
        stream = mock_stream()
        assert isinstance(stream, Stream)
        assert len(stream.items) == 8
        assert all(isinstance(it, Item) for it in stream.items)

    def test_mock_streams_ids(self):
        ids = [s.id for s in mock_streams()]
        assert ids == ["stream-A-granted", "stream-B-escalated", "stream-C-discarded"]
