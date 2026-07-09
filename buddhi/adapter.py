"""The adapter contract: the boundary every adapter implements (interface only).

This module **names the adapter-facing boundary**: the single ``Adapter`` contract
that re-homes the kernel's I/O onto a substrate (an issue tracker's comments, a
task queue, an agent's inbox). It is the surface every adapter imports.

It is **interface only**. It defines no behavior of its own: the three boundary
types are the adapter-facing **names** for types the kernel already owns, and the
four-verb ``Adapter`` Protocol *composes* the existing five seams
(``buddhi.seams``) and the closure orchestration. It introduces no new mechanism
and no second source of policy (the kernel ships ONE policy contract; it does not
scatter policy). No concrete adapter ships here; the runnable reference adapter
lives in ``buddhi/reference/naive_pack.py`` (``NaiveAdapter``).

================================ STOP RULES (interface only) ====================
* **No transport ships here.** ``escalate_async`` delivers via the Escalation
  seam; the kernel holds only the *interface*, never a concrete transport.
* **No substrate I/O ships here.** ``detect_resolved`` reports the OOB seam's
  can-observe-OOB declaration only; the kernel ships no resolver. Each seam's
  reference is the simplest correct behavior: the same posture across all seams.
================================================================================

The three boundary types (adapter-facing names for the kernel's own types):

  ``DecisionItem``  what an adapter **ingests** from its substrate, *before* Stage 0
                    conditions it into the loop's typed ``Item``. == ``RawItem``.
  ``Budget``        the per-run iteration constraint passed to ``run_embedded``.
                    == ``IterationBudget``. NOTE: the *aggregate/stream* budget (the
                    graduated ask bar + the two-tier exclusion lattice) lives behind
                    the **Store seam**, not in this type.
  ``PolicyResult``  what the kernel returns per item, the disposition the adapter
                    acts on (DISCARDED / CONVERGED / MODEL_HANDLED / INVALID_ASK /
                    RESOLVED_OOB / ESCALATED / DENIED). == ``ItemOutcome``.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

# The boundary types are the adapter-facing NAMES for types the kernel already
# defines. They are aliases, not new dataclasses. There is exactly one definition
# of each, in its home module, so the names cannot drift from the kernel's own.
from buddhi.closure import ItemOutcome as PolicyResult
from buddhi.decisions.effort_model import IterationBudget as Budget
from buddhi.decisions.validity_and_ask import PreReasonedAsk
from buddhi.stage0.conditioning import RawItem as DecisionItem


@runtime_checkable
class Adapter(Protocol):
    """The contract an adapter implements to re-home the kernel onto a substrate.

    Four verbs, each a thin composition over kernel symbols/seams the kernel
    already ships. The adapter supplies substrate I/O, the kernel supplies the
    decision. An adapter also wires the five seams (PolicyPack / Router / Store /
    EscalationTransport / OOBSource); this Protocol is the **stream-level** surface
    that sits above them.
    """

    def ingest(self) -> Iterable[DecisionItem]:
        """Yield the substrate's item stream as ``DecisionItem`` (== ``RawItem``).

        Substrate-specific reading (an issue tracker's comments, a task queue, an
        agent's inbox). Stage 0 (``conditioning.condition``) then
        conditions these raw items into the typed ``Item`` the loop consumes.
        """
        ...

    def run_embedded(self, item: DecisionItem, budget: Budget) -> PolicyResult:
        """Hand one item to the kernel under ``budget`` and return its disposition.

        Maps onto ``closure.evaluate_item`` / ``supervise_stream``: the adapter
        drives the kernel, which calls back through the Router seam when it chooses
        to spend cognition. Returns a ``PolicyResult`` (== ``ItemOutcome``) the
        adapter acts on.
        """
        ...

    def escalate_async(self, ask: PreReasonedAsk) -> None:
        """Deliver the pre-reasoned ask to a human, asynchronously.

        Routes to the **Escalation transport seam**. The kernel holds only the
        interface; this method NEVER embeds a transport. The ask is
        control-plane-shaped: 2-4 pre-reasoned ``Option``s with a starred
        recommendation + a warranted-escalation ``confidence`` (a decidable
        question, not an allow/deny gate). The rich options ride the channel
        message body, decoupled from any native approval primitive.
        """
        ...

    def detect_resolved(self, item: DecisionItem) -> bool:
        """Report whether this item was resolved out of band (signaled OOB only).

        Composes the **OOB-source seam**: an adapter declares whether its substrate
        can *ever* observe an out-of-band resolution
        (``OOBSource.can_observe_oob``), so the kernel never blocks convergence
        waiting on a signal the substrate cannot produce. When the substrate can
        observe, the adapter performs the substrate-specific check here; the kernel
        itself ships no resolver.
        """
        ...


__all__ = ["DecisionItem", "Budget", "PolicyResult", "Adapter"]
