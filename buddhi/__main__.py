"""Smoke path: import the kernel and run it end-to-end on the naive pack.

Run from ``buddhikernel-staging/public/``:

    python -m buddhi

Exercises all nine kernel elements behind the single policy contract:
Stage 0 (conditioning), the seven decisions (via the single-stream supervisor),
and the closure operator (a stream-of-streams). Also demonstrates the two-tier
exclusion lattice. Light assertions make the smoke path self-checking: any
deviation exits non-zero.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from buddhi.closure import (
    CONVERGED,
    DENIED,
    DISCARDED,
    ESCALATED,
    INVALID_ASK,
    MODEL_HANDLED,
    Stream,
    supervise_stream,
    supervise_stream_of_streams,
)
from buddhi.decisions.aggregate_budget import aggregate_budget
from buddhi.decisions.effort_model import IterationBudget
from buddhi.decisions.judgment_routing import BusinessQuestion
from buddhi.decisions.validity_and_ask import validate_and_ask
from buddhi.adapter import Adapter, Budget, PolicyResult
from buddhi.policy import BudgetKnobs
from buddhi.reference import (
    InMemoryStore,
    NaiveAdapter,
    NaiveRouter,
    NoOOBSource,
    RecordingEscalation,
    mock_raw_items,
    mock_streams,
    naive_policy_pack,
)
from buddhi.stage0.conditioning import Item, RawItem, condition


def _h(title: str) -> None:
    print(f"\n=== {title} ===")


def demo_stage0() -> None:
    """Stage 0: identity pass-through + detection-only trigger hook."""
    _h("Stage 0 — input conditioning (pass-through naive)")
    raw = mock_raw_items()
    items = condition(raw)
    assert len(items) == len(raw), "Stage 0 must be 1:1"
    for r, it in zip(raw, items):
        assert it.payload == r.payload, "pass-through must not rewrite payloads"
    print(f"  conditioned {len(raw)} raw items -> {len(items)} typed items (identity)")

    # The trigger hook is detection-only: it may flag an item, but the naive
    # conditioning does not act on the flag. Payloads pass through unchanged.
    def _retention_trigger(r: RawItem) -> bool:
        return "retention" in r.payload.lower()

    trigger_pack = replace(naive_policy_pack(), stage0_trigger=_retention_trigger)
    flagged = condition(raw, pack=trigger_pack)
    fired = [it.id for it in flagged if it.trigger_fired]
    for r, it in zip(raw, flagged):
        assert it.payload == r.payload, "trigger detection must not rewrite payloads"
    print(f"  trigger hook fired (detection only) on: {fired or 'none'}")


def demo_single_stream() -> None:
    """The seven decisions over one rich stream (every branch exercised)."""
    _h("Control loop — seven decisions over a single stream")
    pack = naive_policy_pack()
    store = InMemoryStore()
    store.exclude_transient("flaky-source")  # pre-exclude to exercise the lattice
    router = NaiveRouter()
    escalation = RecordingEscalation()
    oob = NoOOBSource()
    budget = IterationBudget(rounds_remaining=3, max_rounds=3)

    items = tuple(condition(mock_raw_items()))
    result = supervise_stream(
        Stream(id="single", items=items), pack, router, store, escalation, oob, budget
    )
    by_id = {o.item_id: o for o in result.outcomes}
    for o in result.outcomes:
        spend = f" [{o.spend.model}/{o.spend.effort}]" if o.spend else ""
        print(f"  {o.status:13} {o.item_id:20}{spend}  {o.detail}")

    expected = {
        "i1-discard": DISCARDED,
        "i2-converged": CONVERGED,
        "i3-model": MODEL_HANDLED,
        "i4-escalate-bypass": ESCALATED,
        "i5-escalate-conf": ESCALATED,
        "i6-deny-marginal": DENIED,
        "i7-invalid": INVALID_ASK,
        "i8-deny-excluded": DENIED,
    }
    for item_id, status in expected.items():
        assert by_id[item_id].status == status, (
            f"{item_id}: expected {status}, got {by_id[item_id].status}"
        )
    assert "excluded" in by_id["i8-deny-excluded"].detail, "i8 must be denied by exclusion"
    assert len(escalation.delivered) == 2, "exactly two asks should be delivered"
    print(f"  -> {len(escalation.delivered)} ask(s) delivered; {result.interrupts_admitted} admitted")


def demo_closure() -> None:
    """The closure operator: allocate across child streams, recurse into granted ones."""
    _h("Closure operator — kernel applied to a stream-of-streams")
    pack = naive_policy_pack()
    store = InMemoryStore()
    router = NaiveRouter()
    escalation = RecordingEscalation()
    oob = NoOOBSource()
    budget = IterationBudget(rounds_remaining=3, max_rounds=3)

    closure = supervise_stream_of_streams(
        "fleet", mock_streams(), pack, router, store, escalation, oob, budget
    )
    children = {c.stream_id: c for c in closure.children}
    for c in closure.children:
        recursed = (
            f"recursed into {len(c.child_result.outcomes)} item(s)"
            if c.child_result
            else "no recursion"
        )
        print(f"  {c.parent_outcome.status:13} {c.stream_id:22}  {recursed}")
        if c.child_result:
            for o in c.child_result.outcomes:
                print(f"        - {o.status:13} {o.item_id}")

    assert children["stream-A-granted"].parent_outcome.status == MODEL_HANDLED
    assert children["stream-A-granted"].child_result is not None, "granted child must recurse"
    assert len(children["stream-A-granted"].child_result.outcomes) == 2
    assert children["stream-B-escalated"].parent_outcome.status == ESCALATED
    assert children["stream-B-escalated"].child_result is None, "escalated child must not recurse"
    assert children["stream-C-discarded"].parent_outcome.status == DISCARDED
    assert children["stream-C-discarded"].child_result is None, "discarded child must not recurse"


def demo_exclusion_lattice() -> None:
    """The two-tier exclusion lattice: transient is retractable; causes never cross."""
    _h("Exclusion lattice — two tiers, causes never crossing")
    pack = naive_policy_pack()
    store = InMemoryStore()

    def ask_for(source: str):
        q = BusinessQuestion(
            item_id="x", source=source, stakes=0.4, model_confidence=0.1,
            question="?", payload="a real payload",
        )
        return validate_and_ask(q, pack)

    # transient tier: retractable (the errored-bucket comeback).
    store.exclude_transient("flaky")
    before = aggregate_budget(ask_for("flaky"), store, pack)
    assert not before.admitted and "excluded" in before.reason
    store.retract_transient("flaky")
    after = aggregate_budget(ask_for("flaky"), store, pack)
    assert "excluded" not in after.reason, "retraction must re-admit the source to judgment"
    print(f"  transient: excluded -> DENY ({before.reason}); retracted -> {after.outcome} ({after.reason})")

    # permanent tier: a transient retraction must NOT cross into it.
    store.exclude_permanent("banned")
    assert store.is_excluded("banned")
    store.retract_transient("banned")  # no-op on the permanent tier
    assert store.is_excluded("banned"), "permanent cap must survive a transient retraction"
    print("  permanent: excluded -> retract_transient is a no-op -> still excluded (causes never cross)")


def demo_adapter() -> None:
    """The adapter contract: ingest -> run_embedded -> escalate, via NaiveAdapter."""
    _h("Adapter contract — ingest / run-embedded / escalate / detect-resolved")
    adapter = NaiveAdapter()
    # The reference adapter satisfies the four-verb Protocol (runtime-checkable).
    assert isinstance(adapter, Adapter), "NaiveAdapter must satisfy the Adapter contract"

    budget = Budget(rounds_remaining=3, max_rounds=3)
    raw_items = tuple(adapter.ingest())
    assert raw_items, "ingest must yield the substrate's item stream"

    for raw in raw_items:
        outcome = adapter.run_embedded(raw, budget)
        assert isinstance(outcome, PolicyResult), "run_embedded must return a PolicyResult"
        print(f"  {outcome.status:13} {outcome.item_id}")

    # run_embedded surfaces escalations via the seam; exercise escalate_async directly.
    assert len(adapter.escalation.delivered) >= 1, "run_embedded must surface escalations"
    _pre = len(adapter.escalation.delivered)
    adapter.escalate_async(adapter.escalation.delivered[0])
    assert len(adapter.escalation.delivered) == _pre + 1, "escalate_async must route through the seam"
    # detect_resolved is the signaled-OOB declaration only; this substrate is blind.
    assert adapter.detect_resolved(raw_items[0]) is False
    print(f"  -> escalate_async called; {len(adapter.escalation.delivered)} ask(s) total via the seam; "
          "detect_resolved=False (substrate declares it cannot observe OOB)")


def demo_hierarchical_budget() -> None:
    """The hierarchical weighted budget: a parent ceiling bounds its subtree.

    Two granted child streams each carry one escalation-worthy item. Under a
    single small shared pool (one interrupt, the degenerate default) the first
    item escalates and the second is denied over the raised bar. Give the fleet a
    parent budget with room and partition it per subtree: each child spends
    against its own scope key, so both escalate, while the parent's ceiling still
    bounds the *total*, because every admit accrues against the root. A third
    subtree would be paced out; the parent never lets its subtree overspend.
    """
    _h("Hierarchical budget — per-subtree scope vs. one shared pool")
    shared_pack = replace(
        naive_policy_pack(),
        budget=BudgetKnobs(daily_interrupt_budget=1, base=0.5, cap=0.95, high_stakes_threshold=0.9),
    )
    # The parent budget has room for both subtrees' first escalation; the root
    # ceiling still bounds their combined spend (it accrues up the tree).
    partitioned_pack = replace(
        naive_policy_pack(),
        budget=BudgetKnobs(daily_interrupt_budget=3, base=0.5, cap=0.95, high_stakes_threshold=0.9),
    )
    router, oob = NaiveRouter(), NoOOBSource()
    budget = IterationBudget(rounds_remaining=3, max_rounds=3)

    def _escalating_child(sid: str) -> Stream:
        # parent: in scope, substantive, mc 0.9 >= 0.6 => MODEL_HANDLED => recurses.
        # item:   routed HUMAN (mc 0.1 < 0.6), confidence 0.7 => escalates if budget allows.
        return Stream(
            id=sid, source=sid, stakes=0.3, model_confidence=0.9, changes=("substantive",),
            items=(Item(id=f"{sid}-1", payload="cross-stream judgment call",
                        source=f"{sid}-rev", stakes=0.5, model_confidence=0.1,
                        changes=("substantive",)),),
        )

    streams = (_escalating_child("alpha"), _escalating_child("beta"))

    def _escalated_items(closure) -> int:
        return sum(
            1
            for c in closure.children if c.child_result
            for o in c.child_result.outcomes if o.status == ESCALATED
        )

    shared = supervise_stream_of_streams(
        "fleet", streams, shared_pack, router, InMemoryStore(), RecordingEscalation(), oob, budget,
        partition_children=False,
    )
    partitioned_store = InMemoryStore()
    partitioned = supervise_stream_of_streams(
        "fleet", streams, partitioned_pack, router, partitioned_store, RecordingEscalation(), oob, budget,
        partition_children=True,
    )
    shared_escalations = _escalated_items(shared)
    partitioned_escalations = _escalated_items(partitioned)
    print(f"  one shared pool (degenerate):   {shared_escalations} child escalation(s) admitted")
    print(f"  per-subtree partitioned budget: {partitioned_escalations} child escalation(s) admitted")
    assert shared_escalations == 1, "shared pool must admit only the first subtree's escalation"
    assert partitioned_escalations == 2, "per-subtree budget must admit both subtrees"
    # Conservation: each subtree's spend accrued against the root, so the parent's
    # count is its whole subtree's total and stays within the parent ceiling.
    assert partitioned_store.interrupts_today() == 2, "the parent accrues its whole subtree's spend"
    assert (
        partitioned_store.interrupts_today() <= partitioned_pack.budget.daily_interrupt_budget
    ), "the parent ceiling bounds the subtree's total spend"


def main() -> int:
    print("buddhi kernel — naive-pack smoke path")
    demo_stage0()
    demo_single_stream()
    demo_closure()
    demo_exclusion_lattice()
    demo_adapter()
    demo_hierarchical_budget()
    print("\nSMOKE PATH OK — kernel imported and ran end-to-end on the naive pack.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
