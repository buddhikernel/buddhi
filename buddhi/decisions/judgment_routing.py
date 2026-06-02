"""Step 4: Model vs. human judgment? (the core routing decision).

Consumes: one item; the pack's judgment taxonomy + ``business_question_threshold``.
Computes: whether the model can decide this item or whether it needs a human.
Emits:    ``JudgmentDecision`` (MODEL, or HUMAN with a routed ``BusinessQuestion``).

The threshold is a pack param: how confident the model must be to decide on its
own. Below it, the item is routed to a human as a business question. This is the
judgment routing at the heart of the kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from buddhi.policy import PolicyPack
    from buddhi.stage0.conditioning import Item

MODEL = "MODEL"
HUMAN = "HUMAN"


@dataclass(frozen=True)
class BusinessQuestion:
    """A routed question for a human, carried into step 5."""

    item_id: str
    source: str
    stakes: float
    model_confidence: float
    question: str
    payload: str


@dataclass(frozen=True)
class JudgmentDecision:
    outcome: str  # MODEL | HUMAN
    question: Optional[BusinessQuestion]
    reason: str
    pack: str

    @property
    def needs_human(self) -> bool:
        return self.outcome == HUMAN


def route_judgment(item: "Item", pack: "PolicyPack") -> JudgmentDecision:
    """Route one item to MODEL or HUMAN. Pure."""
    audit = f"{pack.name}@{pack.version}"
    threshold = pack.judgment.business_question_threshold
    if item.model_confidence >= threshold:
        return JudgmentDecision(
            MODEL, None, f"confidence {item.model_confidence:.2f} >= {threshold:.2f}", audit
        )
    question = BusinessQuestion(
        item_id=item.id,
        source=item.source,
        stakes=item.stakes,
        model_confidence=item.model_confidence,
        question=f"How should item {item.id!r} be handled?",
        payload=item.payload,
    )
    return JudgmentDecision(
        HUMAN, question, f"confidence {item.model_confidence:.2f} < {threshold:.2f}", audit
    )
