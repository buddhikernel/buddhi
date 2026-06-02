"""Step 5: Validity check + async pre-reasoned ask.

Consumes: a routed ``BusinessQuestion``; the pack's validity rules +
          option-generation phrasing.
Computes: whether the question is valid (well-posed) and, if so, 2-4 options
          with a starred recommendation + an escalation confidence.
Emits:    ``PreReasonedAsk`` (question + options + recommendation + confidence)
          or ``InvalidAsk``.

The kernel **pre-reasons** the ask so the human gets a decidable question, not a
raw "what should I do?". The async *delivery* is the Escalation transport seam
(step 5 computes the ask; the seam delivers it). The validity check rejects
malformed questions before they reach a human.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple, Union

from buddhi.decisions.judgment_routing import BusinessQuestion

if TYPE_CHECKING:
    from buddhi.policy import PolicyPack


@dataclass(frozen=True)
class Option:
    label: str
    recommended: bool = False


@dataclass(frozen=True)
class PreReasonedAsk:
    question: BusinessQuestion
    options: Tuple[Option, ...]
    recommended_index: int
    confidence: float  # the kernel's confidence the escalation is warranted (step 7)
    pack: str

    @property
    def is_valid(self) -> bool:
        return True


@dataclass(frozen=True)
class InvalidAsk:
    question: BusinessQuestion
    reason: str
    pack: str

    @property
    def is_valid(self) -> bool:
        return False


AskResult = Union[PreReasonedAsk, InvalidAsk]


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _escalation_confidence(question: BusinessQuestion) -> float:
    """Naive confidence that this escalation is warranted.

    High when stakes are high OR the model is very unsure (it routed here
    because ``model_confidence`` was below the step-4 threshold). The step-7 ask
    bar compares this against the graduated required-confidence.
    """
    return _clamp01(0.5 * question.stakes + 0.5 * (1.0 - question.model_confidence))


def validate_and_ask(question: BusinessQuestion, pack: "PolicyPack") -> AskResult:
    """Validate the question; if valid, pre-reason options + recommendation."""
    audit = f"{pack.name}@{pack.version}"

    # 1. validity: every pack rule must pass (default: no rules => always valid).
    for index, rule in enumerate(pack.validity_rules):
        if not rule(question):
            return InvalidAsk(question, f"failed validity rule[{index}]", audit)

    # 2. options: kernel enforces the universal 2-4 shape; pack values are
    #    advisory bounds that may not exceed these hard limits.
    _MIN_OPTIONS = 2
    _MAX_OPTIONS = 4
    ask = pack.ask
    max_opts = max(0, ask.max_options)
    phrasings = list(ask.option_phrasings)[: min(max_opts, _MAX_OPTIONS)]
    floor = min(max(ask.min_options, _MIN_OPTIONS), _MAX_OPTIONS)
    while len(phrasings) < floor:
        phrasings.append(f"Option {len(phrasings) + 1}")

    # 3. star the recommended option (kernel owns this control-flow choice).
    rec = min(max(ask.recommended_index, 0), len(phrasings) - 1)
    options = tuple(
        Option(label=label, recommended=(i == rec)) for i, label in enumerate(phrasings)
    )

    return PreReasonedAsk(
        question=question,
        options=options,
        recommended_index=rec,
        confidence=_escalation_confidence(question),
        pack=audit,
    )
