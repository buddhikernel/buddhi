"""Step 1: Worth acting on? (cheap, rule-based, pre-model discard gate).

Consumes: one item; the pack's discard predicates.
Computes: whether the item is in scope for this loop.
Emits:    ``KeepDecision`` (KEEP or DISCARD, with a reason for the audit log).

This gate is **cheap**: rule-based, no model call. It runs *before* step 2 so
out-of-scope items never incur model spend. It defaults to **keep-all** when the
pack supplies no discard predicates.

A discard predicate is ``(item) -> bool``: True means "discard this item". A
future adapter may add a cheap-LLM pre-classifier *ahead* of this gate, but that
is NOT kernel scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from buddhi.policy import PolicyPack
    from buddhi.stage0.conditioning import Item

KEEP = "KEEP"
DISCARD = "DISCARD"


@dataclass(frozen=True)
class KeepDecision:
    outcome: str  # KEEP | DISCARD
    reason: str
    pack: str

    @property
    def keep(self) -> bool:
        return self.outcome == KEEP


def worth_acting(item: "Item", pack: "PolicyPack") -> KeepDecision:
    """Return KEEP/DISCARD for one item. Pure; default keep-all."""
    audit = f"{pack.name}@{pack.version}"
    for index, predicate in enumerate(pack.discard_predicates):
        if predicate(item):
            return KeepDecision(DISCARD, f"discarded by predicate[{index}]", audit)
    return KeepDecision(KEEP, "no discard predicate matched", audit)
