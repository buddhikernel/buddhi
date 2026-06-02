"""The adapter contract: boundary types plus the four-verb Adapter Protocol.

Locks that ``buddhi.adapter`` (a) names the three adapter-facing boundary types as
aliases of the kernel's own types (one definition, no drift), (b) defines a
runtime-checkable ``Adapter`` Protocol with the four verbs, and (c) the reference
``NaiveAdapter`` satisfies it by composing the existing seams, with no transport
and no substrate I/O.
"""

from __future__ import annotations

import buddhi
from buddhi.adapter import Adapter, Budget, DecisionItem, PolicyResult
from buddhi.closure import ItemOutcome
from buddhi.decisions.effort_model import IterationBudget
from buddhi.decisions.validity_and_ask import PreReasonedAsk
from buddhi.reference import NaiveAdapter
from buddhi.stage0.conditioning import RawItem


class TestBoundaryTypesAreKernelAliases:
    """The adapter-facing names are aliases of the kernel's own types (no second def)."""

    def test_decision_item_is_raw_item(self):
        assert DecisionItem is RawItem

    def test_budget_is_iteration_budget(self):
        assert Budget is IterationBudget

    def test_policy_result_is_item_outcome(self):
        assert PolicyResult is ItemOutcome

    def test_reexported_from_package_root(self):
        assert buddhi.DecisionItem is RawItem
        assert buddhi.Budget is IterationBudget
        assert buddhi.PolicyResult is ItemOutcome
        assert buddhi.Adapter is Adapter


class TestAdapterProtocol:
    def test_protocol_is_runtime_checkable(self):
        # An object exposing the four verbs satisfies the Protocol.
        assert isinstance(NaiveAdapter(), Adapter)

    def test_incomplete_object_does_not_satisfy(self):
        class Missing:
            def ingest(self):  # missing the other three verbs
                return ()

        assert not isinstance(Missing(), Adapter)


class TestNaiveAdapterComposesSeams:
    def test_ingest_yields_raw_items(self):
        items = tuple(NaiveAdapter().ingest())
        assert items and all(isinstance(i, RawItem) for i in items)

    def test_run_embedded_returns_policy_result(self):
        adapter = NaiveAdapter()
        raw = next(iter(adapter.ingest()))
        outcome = adapter.run_embedded(raw, Budget(3, 3))
        assert isinstance(outcome, PolicyResult)
        assert outcome.status  # a non-empty disposition string

    def test_run_embedded_routes_admitted_asks_to_escalation_seam(self):
        adapter = NaiveAdapter()
        budget = Budget(3, 3)
        for raw in adapter.ingest():
            adapter.run_embedded(raw, budget)
        # at least one item escalates and reaches the (recording) escalation seam.
        assert len(adapter.escalation.delivered) >= 1
        assert all(isinstance(a, PreReasonedAsk) for a in adapter.escalation.delivered)

    def test_detect_resolved_reflects_oob_declaration(self):
        # The naive substrate declares it cannot observe OOB => signaled-only False.
        adapter = NaiveAdapter()
        raw = next(iter(adapter.ingest()))
        assert adapter.detect_resolved(raw) is False
        assert adapter.oob_source.can_observe_oob() is False
