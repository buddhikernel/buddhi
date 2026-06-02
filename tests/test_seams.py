"""Seam conformance: the naive reference adapters satisfy the seam protocols.

The four seam interfaces (Store, Router, EscalationTransport, OOBSource) are
``@runtime_checkable`` Protocols, so conformance is asserted via ``isinstance``.
``RouterPick`` is a frozen value object.
"""

from __future__ import annotations

import dataclasses

import pytest

from buddhi.reference.naive_pack import (
    InMemoryStore,
    NaiveRouter,
    NoOOBSource,
    RecordingEscalation,
)
from buddhi.seams import EscalationTransport, OOBSource, Router, RouterPick, Store


def test_in_memory_store_conforms_to_store():
    assert isinstance(InMemoryStore(), Store)


def test_naive_router_conforms_to_router():
    assert isinstance(NaiveRouter(), Router)


def test_recording_escalation_conforms_to_transport():
    assert isinstance(RecordingEscalation(), EscalationTransport)


def test_no_oob_source_conforms_to_oob_source():
    assert isinstance(NoOOBSource(), OOBSource)


@pytest.mark.parametrize("protocol", [Store, Router, EscalationTransport, OOBSource])
def test_unrelated_object_does_not_conform(protocol):
    # runtime_checkable protocols reject an object missing the required methods.
    assert not isinstance(object(), protocol)


def test_router_pick_is_a_frozen_value_object():
    pick = RouterPick(model="m", effort="high")
    assert (pick.model, pick.effort, pick.rationale) == ("m", "high", "")
    with pytest.raises(dataclasses.FrozenInstanceError):
        pick.effort = "low"  # type: ignore[misc]


# The Store protocol is the only multi-method seam; the single-method seams
# (Router/EscalationTransport/OOBSource) are fully covered by the object() case
# above, but Store's full required method SET needs an all-but-one adversary.
_STORE_METHODS = (
    "interrupts_today",
    "record_interrupt",
    "is_excluded",
    "exclude_permanent",
    "exclude_transient",
    "retract_transient",
)


@pytest.mark.parametrize("omitted", _STORE_METHODS)
def test_store_rejects_adapter_missing_one_method(omitted):
    # An adapter missing exactly one Store method must NOT conform; pins the full
    # required method set, not just "an empty object fails".
    namespace = {
        name: (lambda self, *a, **k: None)
        for name in _STORE_METHODS
        if name != omitted
    }
    near_conformant = type("AlmostStore", (), namespace)
    assert not isinstance(near_conformant(), Store)


def test_store_accepts_adapter_with_full_method_set():
    # The same construction WITH all methods conforms, proving the rejection above
    # is driven by the missing method, not an unrelated construction quirk.
    namespace = {name: (lambda self, *a, **k: None) for name in _STORE_METHODS}
    full = type("FullStore", (), namespace)
    assert isinstance(full(), Store)
