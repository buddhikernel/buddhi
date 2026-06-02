"""Step 2: How much mind to spend? (effort/model bound to the budget).

Consumes: one kept item; the pack's effort taxonomy; the Router seam; the
          current iteration budget + stream ceiling.
Computes: the model/effort pick for this item, **bound** to what the budget and
          the stream ceiling allow.
Emits:    ``SpendDecision`` (model + effort + rationale).

The Router seam does the actual provider selection (a commodity). The kernel
never embeds a provider. It asks the router for a recommendation and **clamps**
it: to the stream ceiling (``effort_taxonomy.ceiling``) and to the iteration
budget (when rounds are nearly exhausted, spend less). The model name comes from
the pack's recommendation for the clamped effort, falling back to the router's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from buddhi.policy import PolicyPack
    from buddhi.seams.router import Router
    from buddhi.stage0.conditioning import Item


@dataclass(frozen=True)
class IterationBudget:
    """The current iteration budget the spend is bound to."""

    rounds_remaining: int
    max_rounds: int


@dataclass(frozen=True)
class SpendDecision:
    model: str
    effort: str
    rationale: str
    pack: str


def decide_spend(
    item: "Item",
    pack: "PolicyPack",
    router: "Router",
    budget: IterationBudget,
    ceiling: Optional[str] = None,
) -> SpendDecision:
    """Bind the router's pick to the iteration budget + stream ceiling."""
    tax = pack.effort_taxonomy
    # Router is a kernel seam: recommend() is contractually non-None; a None return
    # is a seam implementation bug and should raise immediately, not be silently patched.
    pick = router.recommend(item)

    # 1. clamp to the stream ceiling (pack default, or an explicit override).
    effort = tax.clamp(pick.effort, ceiling)
    notes = [f"router={pick.effort}", f"ceiling={ceiling or tax.ceiling}"]

    # 2. bind to the iteration budget: nearly out of rounds => spend less.
    if budget.rounds_remaining <= 1 and tax.rank(effort) > 0:
        effort = tax.downgrade(effort, 1)
        notes.append("downgraded: last round")

    # model is a pack-supplied policy value for the clamped effort (the kernel
    # embeds no provider); fall back to the router's recommendation.
    model = tax.model_by_effort.get(effort, pick.model)
    rationale = "; ".join(notes)
    if pick.rationale:
        rationale = f"{rationale}; {pick.rationale}"
    return SpendDecision(model, effort, rationale, f"{pack.name}@{pack.version}")
