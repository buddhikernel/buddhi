"""Closure / compositionality: the property the package exists to demonstrate.

``evaluate_item`` is the single shared body; ``supervise_stream`` runs it over one
stream's items; ``supervise_stream_of_streams`` treats each child stream *as an
item*, reuses the SAME seven decisions to allocate, and recurses into granted
children. The scale-invariance, recursion-gate, OOB-orchestration, and
cross-stream budget-gating properties are tested explicitly.
"""

from __future__ import annotations

import unittest.mock as mock
from dataclasses import replace

from buddhi import closure as _closure
from buddhi.closure import (
    CONVERGED,
    DENIED,
    DISCARDED,
    ESCALATED,
    INVALID_ASK,
    MODEL_HANDLED,
    RESOLVED_OOB,
    ChildResult,
    ClosureResult,
    ItemOutcome,
    Stream,
    StreamResult,
    evaluate_item,
    subtree_scope,
    supervise_stream,
    supervise_stream_of_streams,
)
from buddhi.decisions.effort_model import IterationBudget
from buddhi.policy import GLOBAL_SCOPE, BudgetKnobs
from buddhi.reference.naive_pack import (
    InMemoryStore,
    NaiveRouter,
    NoOOBSource,
    RecordingEscalation,
    mock_stream,
    mock_streams,
    naive_policy_pack,
)
from buddhi.stage0.conditioning import Item


def _seams():
    return (
        naive_policy_pack(),
        NaiveRouter(),
        InMemoryStore(),
        RecordingEscalation(),
        NoOOBSource(),
    )


def _budget() -> IterationBudget:
    return IterationBudget(rounds_remaining=3, max_rounds=3)


class _CanObserveOOB:
    """An OOB substrate that CAN observe resolutions (so step 6's hook is consulted)."""

    def can_observe_oob(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Base case: supervise_stream
# --------------------------------------------------------------------------- #
def test_supervise_stream_yields_one_outcome_per_item():
    pack, router, store, escalation, oob = _seams()
    stream = mock_stream()
    result = supervise_stream(stream, pack, router, store, escalation, oob, _budget())
    assert isinstance(result, StreamResult)
    assert len(result.outcomes) == len(stream.items)
    assert all(isinstance(o, ItemOutcome) for o in result.outcomes)
    # mock_stream admits exactly two escalations (i4-escalate-bypass, i5-escalate-conf).
    # Pin the literal count rather than re-deriving it with the production formula.
    assert result.interrupts_admitted == 2


def test_supervise_stream_exercises_every_disposition_branch():
    pack, router, store, escalation, oob = _seams()
    store.exclude_transient("flaky-source")  # pre-exclude to drive the lattice branch
    result = supervise_stream(mock_stream(), pack, router, store, escalation, oob, _budget())
    by_id = {o.item_id: o.status for o in result.outcomes}
    assert by_id == {
        "i1-discard": DISCARDED,
        "i2-converged": CONVERGED,
        "i3-model": MODEL_HANDLED,
        "i4-escalate-bypass": ESCALATED,
        "i5-escalate-conf": ESCALATED,
        "i6-deny-marginal": DENIED,
        "i7-invalid": INVALID_ASK,
        "i8-deny-excluded": DENIED,
    }
    assert result.interrupts_admitted == 2
    assert len(escalation.delivered) == 2
    # The i4 high-stakes bypass and the i5 admit must each have recorded an interrupt
    # against the shared budget, pinning that the bypass accounts for the interrupt
    # (without this, dropping record_interrupt() from the bypass leaves the disposition
    # map and interrupts_admitted unchanged).
    assert store.interrupts_today() == 2
    assert "excluded" in {o.item_id: o.detail for o in result.outcomes}["i8-deny-excluded"]


# --------------------------------------------------------------------------- #
# Closure operator: supervise_stream_of_streams
# --------------------------------------------------------------------------- #
def test_closure_grants_escalates_and_discards_children():
    pack, router, store, escalation, oob = _seams()
    closure = supervise_stream_of_streams(
        "fleet", mock_streams(), pack, router, store, escalation, oob, _budget()
    )
    assert isinstance(closure, ClosureResult)
    assert closure.parent_id == "fleet"
    children = {c.stream_id: c for c in closure.children}
    assert all(isinstance(c, ChildResult) for c in closure.children)

    granted = children["stream-A-granted"]
    assert granted.parent_outcome.status == MODEL_HANDLED
    assert granted.child_result is not None  # budget granted => recurse
    assert len(granted.child_result.outcomes) == 2  # into A's two items
    # The recursion must apply the seven decisions CORRECTLY inside the granted child,
    # not merely produce the right NUMBER of outcomes.
    assert {o.item_id: o.status for o in granted.child_result.outcomes} == {
        "A1": MODEL_HANDLED,
        "A2": CONVERGED,
    }

    escalated = children["stream-B-escalated"]
    assert escalated.parent_outcome.status == ESCALATED
    assert escalated.child_result is None  # escalated child does not recurse

    discarded = children["stream-C-discarded"]
    assert discarded.parent_outcome.status == DISCARDED
    assert discarded.child_result is None  # discarded child does not recurse


def test_only_model_handled_parents_recurse():
    """The recursion gate fires for MODEL_HANDLED only: a converged parent (step 3)
    and a marginal parent that gets DENIED (step 7) both say 'do not spend more
    here' and must leave child_result is None."""
    pack, router, store, escalation, oob = _seams()
    converged = Stream(
        id="stream-converged", source="team-conv", stakes=0.3, model_confidence=0.9,
        changes=("substantive", "cosmetic"),  # last change cosmetic => CONVERGED as an item
        items=(Item(id="cv1", payload="child item"),),
    )
    denied = Stream(
        id="stream-denied", source="team-deny", stakes=0.3, model_confidence=0.55,
        changes=("substantive",),  # escalation confidence 0.375 < bar 0.5 => DENIED
        items=(Item(id="dn1", payload="child item"),),
    )
    closure = supervise_stream_of_streams(
        "fleet", (converged, denied), pack, router, store, escalation, oob, _budget()
    )
    by_id = {c.stream_id: c for c in closure.children}
    assert by_id["stream-converged"].parent_outcome.status == CONVERGED
    assert by_id["stream-converged"].child_result is None  # converged => no recurse
    assert by_id["stream-denied"].parent_outcome.status == DENIED
    assert by_id["stream-denied"].child_result is None  # denied => no recurse


def test_closure_literally_reuses_evaluate_item_once_per_child():
    """Scale invariance, structurally: the closure calls the SAME shared body
    (evaluate_item) once per child keyed by stream.as_item(), not a bespoke parent
    allocator that merely reproduces statuses."""
    pack, router, store, escalation, oob = _seams()
    streams = mock_streams()
    stream_ids = {s.id for s in streams}
    real_eval = _closure.evaluate_item
    seen = []

    def _spy(item, *args, **kwargs):
        seen.append(item.id)
        return real_eval(item, *args, **kwargs)

    with mock.patch.object(_closure, "evaluate_item", _spy):
        _closure.supervise_stream_of_streams(
            "fleet", streams, pack, router, store, escalation, oob, _budget()
        )
    # Exactly one parent-level evaluate_item call per child, keyed by the stream id;
    # the granted child's recursion adds A1/A2 calls (filtered out here).
    parent_calls = [i for i in seen if i in stream_ids]
    assert sorted(parent_calls) == sorted(stream_ids)


def test_parent_allocation_is_the_same_function_one_level_up():
    """Scale invariance, behaviourally: the parent's verdict on a stream equals
    running the base allocation function (evaluate_item) on that stream viewed as an
    item, AND steps 1-2 are actually traversed at the parent level."""
    pack, router, store, escalation, oob = _seams()
    streams = mock_streams()
    closure = supervise_stream_of_streams(
        "fleet", streams, pack, router, store, escalation, oob, _budget()
    )
    parent_status = {c.stream_id: c.parent_outcome.status for c in closure.children}

    for stream in streams:
        # Re-run the base case on stream.as_item() with independent seams; the
        # disposition must match. The closure reuses the seven decisions.
        p2, r2, s2, e2, o2 = _seams()
        direct = evaluate_item(stream.as_item(), p2, r2, s2, e2, o2, _budget())
        assert direct.status == parent_status[stream.id]

    # Step 2 (decide_spend) is observably traversed at the parent level: a granted
    # (MODEL_HANDLED) parent carries a SpendDecision, while a step-1 DISCARDED parent
    # short-circuits before step 2 and carries none.
    children = {c.stream_id: c for c in closure.children}
    granted = children["stream-A-granted"].parent_outcome
    assert granted.status == MODEL_HANDLED
    assert granted.spend is not None
    discarded = children["stream-C-discarded"].parent_outcome
    assert discarded.status == DISCARDED
    assert discarded.spend is None


# --------------------------------------------------------------------------- #
# Step-6 OOB orchestration: RESOLVED_OOB through the orchestrator
# --------------------------------------------------------------------------- #
def _oob_reaching_item() -> Item:
    # Survives steps 1-5: in scope, substantive (not converged), model_confidence
    # 0.1 < 0.6 (routed HUMAN), non-empty payload (valid ask) => reaches step 6.
    return Item(
        id="oob-target", payload="should we drop this column?",
        source="reviewer-b", stakes=0.5, model_confidence=0.1, changes=("substantive",),
    )


def test_oob_hook_resolves_item_through_evaluate_item():
    """An item that would otherwise ESCALATE is short-circuited to RESOLVED_OOB when
    the substrate can observe OOB and the injected hook reports it was resolved out of
    band, and escalation must NOT fire for it. Pins the otherwise dead step-6 branch
    in evaluate_item (the naive NoOOBSource always returns PENDING)."""
    pack, router, store, escalation, _ = _seams()
    outcome = evaluate_item(
        _oob_reaching_item(), pack, router, store, escalation, _CanObserveOOB(), _budget(),
        oob_hook=lambda it: True,
    )
    assert outcome.status == RESOLVED_OOB
    assert escalation.delivered == []          # OOB-resolved item is never escalated
    assert store.interrupts_today() == 0


def test_oob_hook_returning_false_still_escalates_through_evaluate_item():
    """Negative control: an observable substrate whose hook reports NOT resolved leaves
    the normal step-7 escalation path intact (pins the branch boundary)."""
    pack, router, store, escalation, _ = _seams()
    outcome = evaluate_item(
        _oob_reaching_item(), pack, router, store, escalation, _CanObserveOOB(), _budget(),
        oob_hook=lambda it: False,
    )
    assert outcome.status == ESCALATED
    assert len(escalation.delivered) == 1


def test_oob_hook_is_threaded_through_supervise_stream():
    """The oob_hook passthrough on supervise_stream is live, not dead: an item in a
    stream resolves out of band when the hook fires."""
    pack, router, store, escalation, _ = _seams()
    result = supervise_stream(
        Stream(id="s", items=(_oob_reaching_item(),)),
        pack, router, store, escalation, _CanObserveOOB(), _budget(),
        oob_hook=lambda it: True,
    )
    assert result.outcomes[0].status == RESOLVED_OOB


# --------------------------------------------------------------------------- #
# Closure-level aggregate budget: gating across streams
# --------------------------------------------------------------------------- #
def test_level1_aggregate_budget_gates_across_streams():
    """The shared Store makes the level-1 ask budget bind across sibling streams:
    once one stream's escalation is admitted, an identical sibling is denied because
    the graduated bar rose. This is the closure's aggregate-budget claim."""
    pack = replace(
        naive_policy_pack(),
        budget=BudgetKnobs(daily_interrupt_budget=1, base=0.5, cap=0.95, high_stakes_threshold=0.9),
    )
    router, store, escalation, oob = NaiveRouter(), InMemoryStore(), RecordingEscalation(), NoOOBSource()

    def _human_stream(sid: str) -> Stream:
        # routed to a human (mc < 0.6), marginal stakes (< 0.9), confidence 0.7.
        return Stream(id=sid, source=sid, stakes=0.5, model_confidence=0.1, changes=("substantive",))

    closure = supervise_stream_of_streams(
        "fleet", (_human_stream("s1"), _human_stream("s2")),
        pack, router, store, escalation, oob, _budget(),
    )
    statuses = [c.parent_outcome.status for c in closure.children]
    assert statuses == [ESCALATED, DENIED]  # first admitted, second over the raised bar
    assert store.interrupts_today() == 1
    assert len(escalation.delivered) == 1


# --------------------------------------------------------------------------- #
# Closure per-subtree scope: a parent bounding its own subtree's budget
# --------------------------------------------------------------------------- #
def _one_interrupt_pack():
    """A root budget of exactly one interrupt: the second escalation is denied
    whether or not children are partitioned, because each admit accrues against
    the shared root; the parent ceiling bounds the combined subtree spend."""
    return replace(
        naive_policy_pack(),
        budget=BudgetKnobs(daily_interrupt_budget=1, base=0.5, cap=0.95, high_stakes_threshold=0.9),
    )


def _granted_escalating_child(sid: str) -> Stream:
    # parent (as an item): in scope, substantive, mc 0.9 >= 0.6 => MODEL_HANDLED => recurses.
    # its single item: routed HUMAN (mc 0.1), confidence 0.7 => escalates if its scope's budget allows.
    return Stream(
        id=sid, source=sid, stakes=0.3, model_confidence=0.9, changes=("substantive",),
        items=(Item(id=f"{sid}-1", payload="cross-stream judgment call", source=f"{sid}-rev",
                    stakes=0.5, model_confidence=0.1, changes=("substantive",)),),
    )


def _child_item_statuses(closure):
    return {
        o.item_id: o.status
        for c in closure.children if c.child_result
        for o in c.child_result.outcomes
    }


def _three_interrupt_pack():
    """A parent budget with room for both subtrees' first escalation (and a third
    would be paced out), so partition isolation is observable while the root still
    bounds the combined spend."""
    return replace(
        naive_policy_pack(),
        budget=BudgetKnobs(daily_interrupt_budget=3, base=0.5, cap=0.95, high_stakes_threshold=0.9),
    )


def test_partition_isolates_each_subtree_under_its_own_scope_key():
    """With partition_children on and a parent budget that has room, each granted
    child spends against its OWN scope key, so two contending subtrees both
    escalate. The spend is recorded under each subtree's key, and (because every
    admit accrues against its ancestors) also against the shared root, whose count
    is the whole subtree's total."""
    pack = _three_interrupt_pack()
    router, store, escalation, oob = NaiveRouter(), InMemoryStore(), RecordingEscalation(), NoOOBSource()
    streams = (_granted_escalating_child("alpha"), _granted_escalating_child("beta"))

    closure = supervise_stream_of_streams(
        "fleet", streams, pack, router, store, escalation, oob, _budget(),
        partition_children=True,
    )
    # both parents granted, both recursed, both child items escalate (own scope keys).
    assert all(c.parent_outcome.status == MODEL_HANDLED for c in closure.children)
    assert _child_item_statuses(closure) == {"alpha-1": ESCALATED, "beta-1": ESCALATED}
    assert len(escalation.delivered) == 2
    # each subtree spent against its own key; one child does not draw down the other's.
    assert store.interrupts_today(subtree_scope(GLOBAL_SCOPE, "alpha")) == 1
    assert store.interrupts_today(subtree_scope(GLOBAL_SCOPE, "beta")) == 1
    # the root accrues the whole subtree's spend (each admit accrues up the tree).
    assert store.interrupts_today(GLOBAL_SCOPE) == 2
    assert store.interrupts_today(GLOBAL_SCOPE) <= pack.budget.daily_interrupt_budget


def test_parent_ceiling_bounds_the_partitioned_subtree_sum():
    """Conservation through the closure: with a one-interrupt parent budget,
    partitioning still gives each child its own scope key, but the parent ceiling
    bounds the COMBINED spend. The first subtree escalates; the second is denied
    over the parent's saturated bar, because its spend accrued against the shared
    root. Siblings cannot collectively exceed the parent's ceiling."""
    pack = _one_interrupt_pack()
    router, store, escalation, oob = NaiveRouter(), InMemoryStore(), RecordingEscalation(), NoOOBSource()
    streams = (_granted_escalating_child("alpha"), _granted_escalating_child("beta"))

    closure = supervise_stream_of_streams(
        "fleet", streams, pack, router, store, escalation, oob, _budget(),
        partition_children=True,
    )
    assert _child_item_statuses(closure) == {"alpha-1": ESCALATED, "beta-1": DENIED}
    assert len(escalation.delivered) == 1
    # the parent's count is its whole subtree's total and is bounded by its ceiling.
    assert store.interrupts_today(GLOBAL_SCOPE) == 1
    assert store.interrupts_today(GLOBAL_SCOPE) <= pack.budget.daily_interrupt_budget
    # the admitted spend landed under the first subtree's key; the second never spent.
    assert store.interrupts_today(subtree_scope(GLOBAL_SCOPE, "alpha")) == 1
    assert store.interrupts_today(subtree_scope(GLOBAL_SCOPE, "beta")) == 0


def test_no_partition_shares_one_pool_across_subtrees_reproducing_today():
    """The naive default (no partition): every child recurses under the same global
    scope, so the one-interrupt pool is shared: the first subtree's item escalates
    and the second is denied over the raised bar. This is today's exact behavior."""
    pack = _one_interrupt_pack()
    router, store, escalation, oob = NaiveRouter(), InMemoryStore(), RecordingEscalation(), NoOOBSource()
    streams = (_granted_escalating_child("alpha"), _granted_escalating_child("beta"))

    closure = supervise_stream_of_streams(
        "fleet", streams, pack, router, store, escalation, oob, _budget(),
    )  # partition_children defaults to False
    assert _child_item_statuses(closure) == {"alpha-1": ESCALATED, "beta-1": DENIED}
    assert len(escalation.delivered) == 1
    assert store.interrupts_today(GLOBAL_SCOPE) == 1  # one shared pool
    assert store.interrupts_today(subtree_scope(GLOBAL_SCOPE, "alpha")) == 0  # no per-subtree keys used


def test_subtree_scope_is_a_pure_parent_child_join():
    assert subtree_scope(GLOBAL_SCOPE, "alpha") == f"{GLOBAL_SCOPE}/alpha"
    assert subtree_scope("__global__/alpha", "leaf") == "__global__/alpha/leaf"  # nests cleanly
