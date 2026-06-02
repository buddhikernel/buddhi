"""Step 6: check_oob_resolution (hook interface; naive returns PENDING)."""

from __future__ import annotations

from buddhi.decisions.oob_resolution import (
    PENDING,
    RESOLVED_OOB,
    OOBDecision,
    check_oob_resolution,
)
from buddhi.reference.naive_pack import NoOOBSource
from buddhi.stage0.conditioning import Item


class _CanObserve:
    """A substrate that *can* observe OOB resolutions (so the hook is consulted)."""

    def can_observe_oob(self) -> bool:
        return True


def _item() -> Item:
    return Item(id="i", payload="p")


def test_substrate_that_cannot_observe_is_always_pending():
    decision = check_oob_resolution(_item(), NoOOBSource(), hook=lambda item: True)
    assert isinstance(decision, OOBDecision)
    assert decision.outcome == PENDING
    assert decision.resolved is False
    assert "cannot observe" in decision.reason


def test_observable_substrate_with_no_hook_is_pending():
    decision = check_oob_resolution(_item(), _CanObserve(), hook=None)
    assert decision.resolved is False
    assert "no OOB resolution hook" in decision.reason


def test_observable_substrate_with_hook_returning_true_resolves():
    decision = check_oob_resolution(_item(), _CanObserve(), hook=lambda item: True)
    assert decision.outcome == RESOLVED_OOB
    assert decision.resolved is True


def test_observable_substrate_with_hook_returning_false_is_pending():
    decision = check_oob_resolution(_item(), _CanObserve(), hook=lambda item: False)
    assert decision.outcome == PENDING
    assert decision.resolved is False
    assert "delegated" in decision.reason
