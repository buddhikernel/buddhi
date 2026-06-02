"""The runnable naive reference pack.

Makes every kernel cell runnable out of the box: a naive reference pack ships
with the kernel so it runs end-to-end on its own. These are **competent naive**
fills: sufficient for completeness, NOT the production method. They contain:

  * a concrete ``PolicyPack`` (``naive_policy_pack``)               — the policy
  * ``InMemoryStore``      — Store seam: counters + two-tier exclusion lattice
  * ``NaiveRouter``        — Router seam: stakes-based effort recommendation
  * ``RecordingEscalation``— Escalation seam: records delivered asks (no transport)
  * ``NoOOBSource``        — OOB seam: declares it CANNOT observe OOB

The OOB source declares "cannot observe" so step 6's reference behavior is
``PENDING`` and the loop never blocks on OOB: the simplest correct behavior for
that seam, the same posture as every other reference here.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from buddhi.adapter import Adapter, Budget, DecisionItem, PolicyResult
from buddhi.closure import Stream, evaluate_item
from buddhi.decisions.judgment_routing import BusinessQuestion
from buddhi.decisions.validity_and_ask import PreReasonedAsk
from buddhi.policy import (
    GLOBAL_SCOPE,
    AskPolicy,
    BudgetKnobs,
    ConvergenceHeuristics,
    EffortTaxonomy,
    JudgmentPolicy,
    PolicyPack,
)
from buddhi.seams.router import RouterPick
from buddhi.stage0.conditioning import Item, RawItem, condition


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #
def _out_of_scope(item: Item) -> bool:
    """Naive step-1 discard predicate: items explicitly flagged out of scope."""
    return bool(item.meta.get("out_of_scope", False))


def _question_has_payload(question: BusinessQuestion) -> bool:
    """Naive step-5 validity rule: a question with an empty payload is malformed."""
    return bool(question.payload.strip())


def naive_policy_pack() -> PolicyPack:
    """The single concrete reference pack. Pure policy values + predicates."""
    return PolicyPack(
        name="naive",
        version="1",
        discard_predicates=(_out_of_scope,),
        effort_taxonomy=EffortTaxonomy(
            levels=("low", "medium", "high"),
            ceiling="high",
            model_by_effort={"low": "naive-small", "medium": "naive-mid", "high": "naive-large"},
        ),
        convergence=ConvergenceHeuristics(),
        judgment=JudgmentPolicy(business_question_threshold=0.6),
        validity_rules=(_question_has_payload,),
        ask=AskPolicy(
            option_phrasings=("Proceed as proposed", "Hold and revert", "Defer — need more context"),
            recommended_index=0,
            min_options=2,
            max_options=4,
        ),
        budget=BudgetKnobs(daily_interrupt_budget=3, base=0.5, cap=0.95, high_stakes_threshold=0.9),
        # stage0_trigger defaults to no-op (nothing triggers).
    )


# --------------------------------------------------------------------------- #
# Seam reference adapters
# --------------------------------------------------------------------------- #
class InMemoryStore:
    """Store seam reference: scope-keyed interrupt counters + two-tier lattice.

    Interrupt counts are kept in a per-scope dict, one int per key. The degenerate
    naive caller keys everything under ``GLOBAL_SCOPE`` (the parameter default),
    so the observable behavior is a single shared counter: identical to the prior
    single-int store. When the closure partitions children, ``aggregate_budget``
    records each admit against the subtree key AND every ancestor, so the per-key
    counts here add up the tree: an ancestor key holds its whole subtree's spend.

    The two exclusion tiers (``_permanent`` vs ``_transient``) are global to the
    store (not scope-partitioned) and never cross: ``retract_transient`` touches
    only the transient tier.
    """

    def __init__(self) -> None:
        self._interrupts: Dict[str, int] = {}
        self._permanent: Set[str] = set()
        self._transient: Set[str] = set()

    def interrupts_today(self, scope: str = GLOBAL_SCOPE) -> int:
        return self._interrupts.get(scope, 0)

    def record_interrupt(self, scope: str = GLOBAL_SCOPE) -> None:
        self._interrupts[scope] = self._interrupts.get(scope, 0) + 1

    def is_excluded(self, source: str) -> bool:
        return source in self._permanent or source in self._transient

    def exclude_permanent(self, source: str) -> None:
        self._permanent.add(source)

    def exclude_transient(self, source: str) -> None:
        self._transient.add(source)

    def retract_transient(self, source: str) -> None:
        # Causes never cross tiers: a permanent exclusion is never retracted here.
        self._transient.discard(source)


class NaiveRouter:
    """Router seam reference: recommend effort from the item's stakes.

    Embeds no real provider. The model strings are illustrative placeholders;
    the kernel resolves the actual model from the pack after clamping.
    """

    def recommend(self, item: Item) -> RouterPick:
        if item.stakes >= 0.7:
            effort = "high"
        elif item.stakes >= 0.4:
            effort = "medium"
        else:
            effort = "low"
        return RouterPick(model=f"naive-{effort}", effort=effort, rationale="stakes-based")


class RecordingEscalation:
    """Escalation seam reference: record delivered asks instead of sending them.

    NOT a transport (no Telegram / file / CLI / native approval). It only proves
    the seam is wired. Concrete transports are adapters, out of the kernel.
    """

    def __init__(self) -> None:
        self.delivered: List[PreReasonedAsk] = []

    def deliver(self, ask: PreReasonedAsk) -> None:
        self.delivered.append(ask)


class NoOOBSource:
    """OOB seam reference: this substrate CANNOT observe an OOB resolution.

    So step 6 always returns PENDING and never blocks convergence. No signaled
    resolver ships here. Step 6 is interface-only in the kernel.
    """

    def can_observe_oob(self) -> bool:
        return False


# --------------------------------------------------------------------------- #
# Reference adapter (proves the buddhi.adapter.Adapter contract is satisfiable)
# --------------------------------------------------------------------------- #
class NaiveAdapter(Adapter):
    """Reference adapter: wires the naive seams to satisfy ``buddhi.adapter.Adapter``.

    Competent naive: it composes the existing seam references + the kernel's
    ``evaluate_item`` orchestration; it ships **no** transport
    (``escalate_async`` records via ``RecordingEscalation``; ``detect_resolved``
    only reports the OOB seam's ``can_observe_oob`` declaration, which is
    ``False`` here). It exists to prove the four-verb contract is satisfiable,
    mirroring how the other ``Naive*`` references prove their seams.
    """

    def __init__(self) -> None:
        self.pack = naive_policy_pack()
        self.router = NaiveRouter()
        self.store = InMemoryStore()
        self.escalation = RecordingEscalation()
        self.oob_source = NoOOBSource()

    def ingest(self) -> Tuple[DecisionItem, ...]:
        """Yield the substrate's raw item stream (``DecisionItem`` == ``RawItem``)."""
        return mock_raw_items()

    def run_embedded(self, item: DecisionItem, budget: Budget) -> PolicyResult:
        """Condition one raw item (Stage 0) then run it through the seven decisions."""
        typed: Item = condition([item], pack=self.pack)[0]
        return evaluate_item(
            item=typed,
            pack=self.pack,
            router=self.router,
            store=self.store,
            escalation=self.escalation,
            oob_source=self.oob_source,
            budget=budget,
        )

    def escalate_async(self, ask: PreReasonedAsk) -> None:
        """Deliver the pre-reasoned ask via the Escalation seam (records it here)."""
        self.escalation.deliver(ask)

    def detect_resolved(self, item: DecisionItem) -> bool:
        """Signaled-OOB declaration only: this substrate cannot observe OOB => False."""
        if not self.oob_source.can_observe_oob():
            return False
        # If the substrate can observe OOB, perform the actual check here.
        return False


# --------------------------------------------------------------------------- #
# Mock data (exercises every branch of the seven decisions)
# --------------------------------------------------------------------------- #
def mock_raw_items() -> Tuple[RawItem, ...]:
    """Raw items for Stage 0 to condition (identity pass-through)."""
    return (
        RawItem(id="i1-discard", payload="typo in a generated file", meta={"out_of_scope": True}),
        RawItem(id="i2-converged", payload="polish wording", model_confidence=0.95,
                changes=("substantive", "cosmetic")),
        RawItem(id="i3-model", payload="rename a local variable", model_confidence=0.9,
                changes=("substantive",)),
        RawItem(id="i4-escalate-bypass", payload="change the data-retention default",
                source="reviewer-a", stakes=0.95, model_confidence=0.2, changes=("substantive",)),
        RawItem(id="i5-escalate-conf", payload="should we drop this column?",
                source="reviewer-b", stakes=0.5, model_confidence=0.1, changes=("substantive",)),
        RawItem(id="i6-deny-marginal", payload="bikeshed: tabs vs spaces",
                source="reviewer-c", stakes=0.3, model_confidence=0.55, changes=("substantive",)),
        RawItem(id="i7-invalid", payload="   ", source="reviewer-d", stakes=0.4,
                model_confidence=0.1, changes=("substantive",)),
        RawItem(id="i8-deny-excluded", payload="flaky reviewer pinged again",
                source="flaky-source", stakes=0.4, model_confidence=0.1, changes=("substantive",)),
    )


def mock_stream() -> Stream:
    """A single rich stream (raw items conditioned via Stage 0 by the caller)."""
    # The caller runs Stage 0; here we wrap the already-typed items for convenience.
    from buddhi.stage0.conditioning import condition

    return Stream(id="single", items=tuple(condition(mock_raw_items())))


def mock_streams() -> Tuple[Stream, ...]:
    """A stream-of-streams for the closure operator (allocation across children)."""
    a = Stream(
        id="stream-A-granted",
        source="team-A",
        stakes=0.3,
        model_confidence=0.9,  # parent: MODEL_HANDLED => budget granted => recurse
        changes=("substantive",),
        items=(
            Item(id="A1", payload="resolvable task", model_confidence=0.9, changes=("substantive",)),
            Item(id="A2", payload="already polished", model_confidence=0.9, changes=("substantive", "cosmetic")),
        ),
    )
    b = Stream(
        id="stream-B-escalated",
        source="team-B",
        stakes=0.95,  # parent: HUMAN + high-stakes bypass => ESCALATED (no recursion)
        model_confidence=0.2,
        changes=("substantive",),
        items=(Item(id="B1", payload="cross-stream judgment call", model_confidence=0.2, stakes=0.95),),
    )
    c = Stream(
        id="stream-C-discarded",
        source="team-C",
        meta={"out_of_scope": True},  # parent: DISCARDED (no recursion)
        items=(Item(id="C1", payload="not in scope"),),
    )
    return (a, b, c)
