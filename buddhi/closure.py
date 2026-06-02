"""The closure / compositionality operator: the kernel applied to a stream-of-streams.

Design property: the kernel is **scale-invariant**. A supervisor that allocates a
cognitive budget across supervisors is *the same allocation function* applied one
level up. Only what counts as an "item" and a "stream" changes. "How much
cognition to spend on this item" becomes "how much budget to grant this work
stream."

This module ships a **competent naive** of that property, in two parts:

  * ``supervise_stream``           — the base case: run the seven decisions, in
                                     order, over the items of ONE stream.
  * ``supervise_stream_of_streams``— the closure operator: treat each child
                                     stream **as an item**, reuse the SAME seven
                                     decisions to allocate, and recurse into the
                                     items of each granted child.

ALLOCATION-RECURSION ONLY. There is **no** inter-stream coordination, conflict
avoidance, work partitioning, or locking. Those belong to a different
(coordination) layer, outside the kernel. The shared Store does budget
*accounting* across children (that is step 7's aggregate budget); it never
coordinates work between streams.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Optional, Tuple

from buddhi.decisions.aggregate_budget import aggregate_budget
from buddhi.decisions.convergence import has_converged
from buddhi.decisions.effort_model import IterationBudget, SpendDecision, decide_spend
from buddhi.decisions.judgment_routing import route_judgment
from buddhi.decisions.oob_resolution import OOBResolutionHook, check_oob_resolution
from buddhi.decisions.validity_and_ask import PreReasonedAsk, validate_and_ask
from buddhi.decisions.worth_acting import worth_acting
from buddhi.policy import GLOBAL_SCOPE
from buddhi.stage0.conditioning import Item

if TYPE_CHECKING:
    from buddhi.policy import PolicyPack
    from buddhi.seams.escalation import EscalationTransport
    from buddhi.seams.oob_source import OOBSource
    from buddhi.seams.router import Router
    from buddhi.seams.store import Store


def subtree_scope(parent_scope: str, child_id: str) -> str:
    """Derive a child stream's budget scope from its parent's scope.

    The closure uses this to give each subtree its own budget partition when
    ``partition_children`` is on. The result is a path in the budget tree, so a
    parent can subdivide its allowance across children while still bounding their
    combined spend. ``aggregate_budget`` accrues each admit up the path, and
    ``policy.scope_ancestors`` is the inverse that recovers the ancestor chain
    (step 7's hierarchical weighted budget).

    ``child_id`` is percent-encoded (``%`` → ``%25``, then ``/`` → ``%2F``)
    before joining so that ids containing ``/`` cannot collide with a deeper
    parent/child split: e.g. parent ``__global__`` + child ``a/b`` becomes
    ``__global__/a%2Fb``, which is distinct from parent ``__global__/a`` +
    child ``b`` (``__global__/a/b``).
    """
    escaped = child_id.replace("%", "%25").replace("/", "%2F")
    return f"{parent_scope}/{escaped}"


# Item dispositions after one pass of the seven decisions.
DISCARDED = "DISCARDED"
CONVERGED = "CONVERGED"
MODEL_HANDLED = "MODEL_HANDLED"
INVALID_ASK = "INVALID_ASK"
RESOLVED_OOB = "RESOLVED_OOB"
ESCALATED = "ESCALATED"
DENIED = "DENIED"


@dataclass(frozen=True)
class ItemOutcome:
    """The disposition of one item after a single pass of the seven decisions."""

    item_id: str
    status: str
    detail: str
    spend: Optional[SpendDecision] = None
    ask: Optional[PreReasonedAsk] = None


@dataclass(frozen=True)
class Stream:
    """A work stream: a set of items, plus the attributes that let the stream
    itself be treated as an item by a parent kernel (the closure recursion)."""

    id: str
    items: Tuple[Item, ...] = ()
    # stream-as-item attributes (consumed by the parent kernel):
    source: str = "stream"
    stakes: float = 0.0
    model_confidence: float = 1.0
    changes: Tuple[str, ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)

    def as_item(self) -> Item:
        """View this stream as a single item for the parent kernel."""
        return Item(
            id=self.id,
            payload=f"<stream {self.id}: {len(self.items)} item(s)>",
            source=self.source,
            stakes=self.stakes,
            model_confidence=self.model_confidence,
            changes=self.changes,
            meta=self.meta,
        )


@dataclass(frozen=True)
class StreamResult:
    stream_id: str
    outcomes: Tuple[ItemOutcome, ...]
    interrupts_admitted: int


@dataclass(frozen=True)
class ChildResult:
    """A parent's verdict on a child stream, plus the recursion if budget was granted."""

    stream_id: str
    parent_outcome: ItemOutcome
    child_result: Optional[StreamResult]


@dataclass(frozen=True)
class ClosureResult:
    parent_id: str
    children: Tuple[ChildResult, ...]


def evaluate_item(
    item: Item,
    pack: "PolicyPack",
    router: "Router",
    store: "Store",
    escalation: "EscalationTransport",
    oob_source: "OOBSource",
    budget: IterationBudget,
    oob_hook: Optional[OOBResolutionHook] = None,
    scope: str = GLOBAL_SCOPE,
) -> ItemOutcome:
    """Run the seven decisions, in order, over one item. Pure orchestration.

    This is the single shared body reused by both the per-item base case and the
    closure recursion (where the "item" is a child stream viewed as an item), so
    the closure literally *reuses the seven decisions*.

    ``scope`` is the budget scope step 7 accounts this item's interrupt under
    (step 7's hierarchical weighted budget). It defaults to ``GLOBAL_SCOPE`` (the
    single shared pool), so every existing caller is unchanged.
    """
    # 1: worth acting on?
    keep = worth_acting(item, pack)
    if not keep.keep:
        return ItemOutcome(item.id, DISCARDED, keep.reason)

    # 2: how much mind to spend?
    spend = decide_spend(item, pack, router, budget)

    # 3: has it converged?
    conv = has_converged(item, pack)
    if conv.converged:
        return ItemOutcome(item.id, CONVERGED, conv.reason, spend=spend)

    # 4: model judgment or human judgment?
    judgment = route_judgment(item, pack)
    if not judgment.needs_human:
        return ItemOutcome(item.id, MODEL_HANDLED, judgment.reason, spend=spend)

    # 5: validity check + pre-reasoned ask.
    ask = validate_and_ask(judgment.question, pack)
    if not ask.is_valid:
        return ItemOutcome(item.id, INVALID_ASK, ask.reason, spend=spend)

    # 6: resolved out of band? In the naive, the OOB source declares it cannot
    # observe, so this is always PENDING.
    oob = check_oob_resolution(item, oob_source, oob_hook)
    if oob.resolved:
        return ItemOutcome(item.id, RESOLVED_OOB, oob.reason, spend=spend, ask=ask)

    # 7: aggregate stream budget (graduated ask bar + exclusion lattice),
    #     accounted under this item's budget scope.
    admit = aggregate_budget(ask, store, pack, scope)
    if admit.admitted:
        escalation.deliver(ask)
        return ItemOutcome(item.id, ESCALATED, admit.reason, spend=spend, ask=ask)
    return ItemOutcome(item.id, DENIED, admit.reason, spend=spend, ask=ask)


def supervise_stream(
    stream: Stream,
    pack: "PolicyPack",
    router: "Router",
    store: "Store",
    escalation: "EscalationTransport",
    oob_source: "OOBSource",
    budget: IterationBudget,
    oob_hook: Optional[OOBResolutionHook] = None,
    scope: str = GLOBAL_SCOPE,
) -> StreamResult:
    """Base case: apply the seven decisions to every item of one stream.

    Every item is accounted under ``scope`` (default ``GLOBAL_SCOPE``), so one
    stream's items share one budget partition.
    """
    outcomes = tuple(
        evaluate_item(item, pack, router, store, escalation, oob_source, budget, oob_hook, scope)
        for item in stream.items
    )
    admitted = sum(1 for o in outcomes if o.status == ESCALATED)
    return StreamResult(stream.id, outcomes, admitted)


def supervise_stream_of_streams(
    parent_id: str,
    streams: Tuple[Stream, ...],
    pack: "PolicyPack",
    router: "Router",
    store: "Store",
    escalation: "EscalationTransport",
    oob_source: "OOBSource",
    budget: IterationBudget,
    oob_hook: Optional[OOBResolutionHook] = None,
    scope: str = GLOBAL_SCOPE,
    partition_children: bool = False,
) -> ClosureResult:
    """The closure operator: allocate across child streams, then recurse.

    Each child stream is viewed *as an item* and run through the same seven
    decisions (allocation). When the parent keeps a child and the model can
    manage it (``MODEL_HANDLED``), budget is granted and the kernel recurses into
    that child's items via ``supervise_stream``. Allocation-recursion only.

    The parent allocates under ``scope`` (so the parent-level allocations across
    siblings share one pool, the prior behavior). For each granted child, the
    recursion's budget scope is the **per-subtree scope** when
    ``partition_children`` is on (``subtree_scope(scope, stream.id)``), so each
    child spends against its own scope key while its spend still accrues up to
    ``scope``: the parent ceiling bounds the children's combined spend, and one
    child cannot draw down another's allowance. The naive default
    (``partition_children=False``) keeps every child under the same ``scope`` (one
    global pool, no partition), which reproduces today's behavior exactly.
    """
    children = []
    for stream in streams:
        parent_outcome = evaluate_item(
            stream.as_item(), pack, router, store, escalation, oob_source, budget, oob_hook, scope
        )
        child_result: Optional[StreamResult] = None
        # Budget granted => recurse one level down into the child's own items.
        if parent_outcome.status == MODEL_HANDLED:
            child_scope = subtree_scope(scope, stream.id) if partition_children else scope
            child_result = supervise_stream(
                stream, pack, router, store, escalation, oob_source, budget, oob_hook, child_scope
            )
        children.append(ChildResult(stream.id, parent_outcome, child_result))
    return ClosureResult(parent_id, tuple(children))
