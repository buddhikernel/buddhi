"""Step 3: has_converged, accounted_changes, and bounded_retry."""

from __future__ import annotations

import pytest

from buddhi.decisions.convergence import (
    CONTINUE,
    CONVERGED,
    ConvergenceDecision,
    TransientFailure,
    accounted_changes,
    bounded_retry,
    has_converged,
)
from buddhi.policy import ConvergenceHeuristics, PolicyPack
from buddhi.reference.naive_pack import naive_policy_pack
from buddhi.stage0.conditioning import Item


def _item(changes) -> Item:
    return Item(id="x", payload="p", changes=tuple(changes))


# --------------------------------------------------------------------------- #
# accounted_changes
# --------------------------------------------------------------------------- #
def test_accounted_changes_filters_transient_failures():
    pack = naive_policy_pack()
    item = _item(("substantive", "transient_failure", "cosmetic"))
    assert accounted_changes(item, pack) == ("substantive", "cosmetic")


def test_accounted_changes_empty_when_only_transient():
    pack = naive_policy_pack()
    assert accounted_changes(_item(("transient_failure", "transient_failure")), pack) == ()


# --------------------------------------------------------------------------- #
# has_converged
# --------------------------------------------------------------------------- #
def test_no_changes_is_continue():
    decision = has_converged(_item(()), naive_policy_pack())
    assert isinstance(decision, ConvergenceDecision)
    assert decision.outcome == CONTINUE
    assert decision.converged is False


def test_last_substantive_is_continue():
    decision = has_converged(_item(("cosmetic", "substantive")), naive_policy_pack())
    assert decision.outcome == CONTINUE
    assert decision.converged is False


def test_last_cosmetic_is_converged():
    decision = has_converged(_item(("substantive", "cosmetic")), naive_policy_pack())
    assert decision.outcome == CONVERGED
    assert decision.converged is True


def test_only_transient_history_is_continue():
    # transient failures are excluded from accounting => nothing acted on yet.
    decision = has_converged(_item(("transient_failure",)), naive_policy_pack())
    assert decision.converged is False
    assert "no accounted change" in decision.reason


def test_unknown_kind_conservatively_continues():
    decision = has_converged(_item(("mystery",)), naive_policy_pack())
    assert decision.converged is False
    assert "unclassified" in decision.reason


# --------------------------------------------------------------------------- #
# bounded_retry
# --------------------------------------------------------------------------- #
class _Flaky:
    """A callable that raises TransientFailure for the first ``fail_times`` calls."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TransientFailure(f"flake #{self.calls}")
        return "ok"


def test_succeeds_within_the_retry_bound():
    pack = naive_policy_pack()  # max_transient_retries=2 => 3 attempts
    flaky = _Flaky(fail_times=2)
    assert bounded_retry(flaky, pack) == "ok"
    assert flaky.calls == 3


def test_succeeds_first_try_without_retrying():
    flaky = _Flaky(fail_times=0)
    assert bounded_retry(flaky, naive_policy_pack()) == "ok"
    assert flaky.calls == 1


def test_reraises_once_bound_is_exceeded():
    pack = naive_policy_pack()  # 3 attempts total
    flaky = _Flaky(fail_times=99)  # always fails
    with pytest.raises(TransientFailure):
        bounded_retry(flaky, pack)
    assert flaky.calls == 3  # exactly max_transient_retries + 1 attempts


def test_retry_bound_honours_custom_pack():
    pack = PolicyPack(
        name="p", version="1",
        convergence=ConvergenceHeuristics(max_transient_retries=0),  # 1 attempt only
    )
    flaky = _Flaky(fail_times=99)
    with pytest.raises(TransientFailure):
        bounded_retry(flaky, pack)
    assert flaky.calls == 1


def test_non_transient_exception_propagates_immediately():
    def boom():
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        bounded_retry(boom, naive_policy_pack())
