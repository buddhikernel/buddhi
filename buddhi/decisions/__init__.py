"""The seven decision functions: one module per step.

  1  worth_acting.py      worth_acting          -> KeepDecision
  2  effort_model.py      decide_spend          -> SpendDecision
  3  convergence.py       has_converged         -> ConvergenceDecision
  4  judgment_routing.py  route_judgment        -> JudgmentDecision
  5  validity_and_ask.py  validate_and_ask      -> PreReasonedAsk | InvalidAsk
  6  oob_resolution.py    check_oob_resolution  -> OOBDecision
  7  aggregate_budget.py  aggregate_budget      -> AdmitDecision

Every decision is a pure function of explicit inputs (the Store is an injected
seam, not ambient state).
"""

from __future__ import annotations

from buddhi.decisions.aggregate_budget import (
    AdmitDecision,
    aggregate_budget,
    required_confidence,
)
from buddhi.decisions.convergence import (
    ConvergenceDecision,
    TransientFailure,
    accounted_changes,
    bounded_retry,
    has_converged,
)
from buddhi.decisions.effort_model import IterationBudget, SpendDecision, decide_spend
from buddhi.decisions.judgment_routing import (
    BusinessQuestion,
    JudgmentDecision,
    route_judgment,
)
from buddhi.decisions.oob_resolution import (
    OOBDecision,
    OOBResolutionHook,
    check_oob_resolution,
)
from buddhi.decisions.validity_and_ask import (
    InvalidAsk,
    Option,
    PreReasonedAsk,
    validate_and_ask,
)
from buddhi.decisions.worth_acting import KeepDecision, worth_acting

__all__ = [
    # step 1
    "worth_acting",
    "KeepDecision",
    # step 2
    "decide_spend",
    "SpendDecision",
    "IterationBudget",
    # step 3
    "has_converged",
    "ConvergenceDecision",
    "accounted_changes",
    "bounded_retry",
    "TransientFailure",
    # step 4
    "route_judgment",
    "JudgmentDecision",
    "BusinessQuestion",
    # step 5
    "validate_and_ask",
    "PreReasonedAsk",
    "InvalidAsk",
    "Option",
    # step 6
    "check_oob_resolution",
    "OOBDecision",
    "OOBResolutionHook",
    # step 7
    "aggregate_budget",
    "AdmitDecision",
    "required_confidence",
]
