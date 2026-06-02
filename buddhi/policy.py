"""The single PolicyPack contract: the one policy source for the kernel.

This module is the *single* place policy lives: the kernel ships ONE policy
contract and does not scatter policy across modules.

The kernel owns *mechanism* (control flow); a ``PolicyPack`` supplies *judgment*
(taxonomies, thresholds, phrasing, predicates) at each of the seven decisions
plus Stage 0. A pack is **runtime-neutral**: it carries pure policy values and
predicates only: no ``cwd``, no env, no substrate config.

The pack is a *contract*, not an implementation. The kernel also ships a runnable
reference implementation in ``buddhi/reference/naive_pack.py`` for smoke tests and
examples; production consumers should supply their own pack.

Per-step policy:

  step 1  discard predicates           -> ``discard_predicates``
  step 2  effort taxonomy + model recs -> ``effort_taxonomy``
  step 3  convergence heuristics       -> ``convergence``
  step 4  judgment + threshold         -> ``judgment``
  step 5  validity rules + phrasing     -> ``validity_rules`` + ``ask``
  step 6  OOB-source declaration        -> the OOBSource **seam**, not a pack field
  step 7  budget knobs                  -> ``budget``
  Stage 0 trigger-detection hook        -> ``stage0_trigger`` (defaults to no-op)
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Sequence, Tuple

if TYPE_CHECKING:  # annotations only: never imported at runtime (no import cycle)
    from buddhi.stage0.conditioning import Item, RawItem


# A discard predicate returns True when an item should be DISCARDED (out of
# scope). Typed loosely here so policy.py imports nothing from the decision or
# Stage 0 modules (keeps the dependency graph acyclic).
DiscardPredicate = Callable[["Item"], bool]
# A validity rule returns True when a routed business question is well-posed.
ValidityRule = Callable[[Any], bool]
# Stage 0 trigger-detection hook: (raw item) -> bool ("did a conditioning
# trigger fire for this item?"). Detection only: the naive conditioning records
# the result but does not act on it (see stage0/conditioning.py).
TriggerHook = Callable[["RawItem"], bool]


def _no_trigger(_raw: "RawItem") -> bool:
    """Default Stage 0 trigger hook: nothing ever triggers (no-op)."""
    return False


@dataclass(frozen=True)
class EffortTaxonomy:
    """Step 2 policy: the effort levels the router pick is clamped to.

    ``levels`` is ordered cheapest -> most expensive. ``ceiling`` is the most
    expensive level this stream is allowed to spend (the per-stream ceiling the
    kernel binds the router's pick to). ``model_by_effort`` is the pack's model
    recommendation per effort level. The kernel never embeds a provider; it
    only clamps the router's recommendation to the budget and ceiling.
    """

    levels: Tuple[str, ...] = ("low", "medium", "high")
    ceiling: str = "high"
    model_by_effort: Mapping[str, str] = field(
        default_factory=lambda: {"low": "small", "medium": "mid", "high": "large"}
    )

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError("EffortTaxonomy levels cannot be empty")
        if self.ceiling not in self.levels:
            raise ValueError(f"ceiling '{self.ceiling}' must be one of the levels: {self.levels}")

    def rank(self, level: str) -> int:
        return self.levels.index(level)

    def clamp(self, level: str, ceiling: str | None = None) -> str:
        """Return ``level``, lowered to ``ceiling`` if it exceeds it."""
        cap = ceiling if ceiling is not None else self.ceiling
        if cap not in self.levels:
            cap = self.ceiling if self.ceiling in self.levels else self.levels[-1]
        if level not in self.levels:
            return cap
        return level if self.rank(level) <= self.rank(cap) else cap

    def downgrade(self, level: str, steps: int = 1) -> str:
        """Lower ``level`` by ``steps`` (never below the cheapest)."""
        if level not in self.levels:
            return self.levels[0]
        return self.levels[max(0, self.rank(level) - steps)]


@dataclass(frozen=True)
class ConvergenceHeuristics:
    """Step 3 policy: the substantive-vs-cosmetic change definition.

    Only ``substantive`` changes reset the convergence clock. ``cosmetic``
    changes do not. ``transient`` changes are a bounded-retry failure class that
    is **excluded from convergence accounting** entirely (a transient failure is
    neither progress nor non-progress; it simply retries).
    """

    substantive_kinds: Tuple[str, ...] = ("substantive",)
    cosmetic_kinds: Tuple[str, ...] = ("cosmetic", "polish")
    transient_kinds: Tuple[str, ...] = ("transient_failure",)
    # Max bounded retries for the transient-failure class: a plain count (no
    # delay, no backoff).
    max_transient_retries: int = 2

    def is_substantive(self, kind: str) -> bool:
        return kind in self.substantive_kinds

    def is_cosmetic(self, kind: str) -> bool:
        return kind in self.cosmetic_kinds

    def is_transient(self, kind: str) -> bool:
        return kind in self.transient_kinds


@dataclass(frozen=True)
class JudgmentPolicy:
    """Step 4 policy: when the model must defer to a human.

    ``business_question_threshold`` is the minimum model self-confidence
    required for the model to decide an item on its own. Below it, the item is
    routed to a human as a business question.
    """

    business_question_threshold: float = 0.6


@dataclass(frozen=True)
class AskPolicy:
    """Step 5 policy: how to pre-reason an ask.

    The kernel owns the control flow (clamp to 2-4 options, star one); the pack
    supplies the candidate option phrasings and which index to recommend.
    """

    option_phrasings: Tuple[str, ...] = ("Proceed as proposed", "Hold and revert")
    recommended_index: int = 0
    min_options: int = 2
    max_options: int = 4


# The default budget scope. Interrupt accounting is partitioned by a *scope key*
# (a stream id, a subtree id, or any opaque string). A pack that supplies no
# per-scope configuration leaves every scope under this one global key, which
# collapses the hierarchy to a single shared pool: the degenerate case.
GLOBAL_SCOPE = "__global__"


def scope_ancestors(scope: str) -> Tuple[str, ...]:
    """The scope and all of its ancestors, root first.

    A scope key is a ``/``-joined path (the join is ``closure.subtree_scope``,
    which percent-encodes each child id so a literal ``/`` only ever marks a
    parent/child boundary). Its ancestors are the progressive path prefixes:
    ``"r/a/b"`` -> ``("r", "r/a", "r/a/b")``. A scope with no ``/`` is its own
    root and yields just itself, so a flat (degenerate) scope has exactly one
    ancestor and every hierarchical computation below collapses to the
    single-scope case.
    """
    segments = scope.split("/")
    return tuple("/".join(segments[: i + 1]) for i in range(len(segments)))


@dataclass(frozen=True)
class ScopeAllocation:
    """The per-scope budget allocation in the hierarchical weighted model.

    A budget is no longer a single global pool: it is a tree of *scopes*, each
    carrying a ``weight`` (relative priority) and an absolute interrupt
    ``ceiling``. This object holds one scope's allocation.

      * ``weight``  : a **local** scalar on this scope's own ceiling (NOT a
                      relative share of a shared pool; the contention-aware
                      relative-share / dual-price form is out of scope for the
                      naive contract). ``1.0`` is the degenerate identity.
      * ``ceiling`` : this scope's absolute interrupt ceiling. ``None`` means
                      "inherit the root ceiling" (``daily_interrupt_budget``),
                      which is the degenerate default.

    The degenerate allocation (``ScopeAllocation()``) is weight ``1.0`` and an
    inherited (root) ceiling, so a scope with no explicit configuration behaves
    exactly like today's single shared pool.
    """

    weight: float = 1.0
    ceiling: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.weight) or self.weight <= 0.0:
            raise ValueError(f"ScopeAllocation.weight must be a finite positive number, got {self.weight}")
        if self.ceiling is not None:
            if not isinstance(self.ceiling, int) or isinstance(self.ceiling, bool):
                raise TypeError(f"ScopeAllocation.ceiling must be an int, got {type(self.ceiling).__name__}")
            if self.ceiling < 1:
                raise ValueError(f"ScopeAllocation.ceiling must be >= 1 when set, got {self.ceiling}")


# The degenerate allocation, reused so an unconfigured scope is a single object.
_DEGENERATE_ALLOCATION = ScopeAllocation()


@dataclass(frozen=True)
class BudgetKnobs:
    """Step 7 policy: a hierarchical weighted interrupt allocation.

    The budget is a tree of scopes (see ``ScopeAllocation``). ``daily_interrupt_budget``
    is the **root (default-scope) ceiling**; ``scope_allocations`` optionally
    overrides the weight and/or ceiling of named child scopes. The graduated ask
    bar for a scope ramps linearly from ``base`` (zero spend) to ``cap`` (full
    spend) in ``interrupts_today(scope) / max(1, effective_ceiling(scope))``. An
    item whose stakes are ``>= high_stakes_threshold`` bypasses the bar.

    **Degenerate (shared-pool) case.** With an empty ``scope_allocations`` every
    scope inherits weight ``1.0`` and ceiling = ``daily_interrupt_budget``, so
    ``effective_ceiling(scope) == daily_interrupt_budget`` for every scope. A
    depth-1 tree with uniform weights and every ceiling equal to the root budget
    collapses to a single shared global pool: the prior behavior, exactly.

    **Hierarchical bound.** ``effective_ceiling(scope)`` is the minimum over the
    scope and every one of its ancestors, so a parent's ceiling is a hard upper
    bound on every scope beneath it. A subtree can subdivide its parent's
    allowance but never enlarge it. Paired with ancestor accrual in
    ``aggregate_budget`` (each admitted interrupt is charged to the scope and all
    of its ancestors), the parent ceiling bounds the *total* its subtree can spend
    through the graduated bar.
    """

    daily_interrupt_budget: int = 5
    base: float = 0.5
    cap: float = 0.95
    high_stakes_threshold: float = 0.9
    # Per-scope overrides. Empty => every scope inherits the degenerate defaults
    # (weight 1.0, ceiling = daily_interrupt_budget), i.e. the single shared pool.
    scope_allocations: Mapping[str, ScopeAllocation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, val in (("base", self.base), ("cap", self.cap), ("high_stakes_threshold", self.high_stakes_threshold)):
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"BudgetKnobs.{name} must be in [0, 1], got {val}")
        if self.cap < self.base:
            raise ValueError(
                f"BudgetKnobs.cap ({self.cap}) must be >= base ({self.base}); "
                "the ask bar must rise from zero-spend floor to saturated-budget cap"
            )
        if self.daily_interrupt_budget < 1:
            raise ValueError(f"BudgetKnobs.daily_interrupt_budget must be >= 1, got {self.daily_interrupt_budget}")
        if self.scope_allocations is None:
            raise TypeError("BudgetKnobs.scope_allocations cannot be None")
        if not isinstance(self.scope_allocations, Mapping):
            raise TypeError(
                f"BudgetKnobs.scope_allocations must be a Mapping, got {type(self.scope_allocations).__name__}"
            )
        for scope, alloc in self.scope_allocations.items():
            if not isinstance(scope, str):
                raise TypeError(
                    f"scope_allocations key must be a str, got {type(scope).__name__}"
                )
            if not isinstance(alloc, ScopeAllocation):
                raise TypeError(
                    f"scope_allocations[{scope!r}] must be a ScopeAllocation, got {type(alloc).__name__}"
                )

    def allocation_for(self, scope: str = GLOBAL_SCOPE) -> ScopeAllocation:
        """The allocation for ``scope``: an explicit override or the degenerate default."""
        return self.scope_allocations.get(scope, _DEGENERATE_ALLOCATION)

    def weight_for(self, scope: str = GLOBAL_SCOPE) -> float:
        """The relative weight of ``scope`` (``1.0`` when unconfigured)."""
        return self.allocation_for(scope).weight

    def _local_ceiling(self, scope: str) -> int:
        """One scope's own ceiling, ignoring its ancestors.

        The scope's ceiling (its own override, else the root budget) scaled by its
        weight, floored at 1 and clamped to the root budget.
        """
        alloc = self.allocation_for(scope)
        ceiling = alloc.ceiling if alloc.ceiling is not None else self.daily_interrupt_budget
        scaled = int(alloc.weight * ceiling + 0.5)
        return max(1, min(self.daily_interrupt_budget, scaled))

    def effective_ceiling(self, scope: str = GLOBAL_SCOPE) -> int:
        """The interrupt ceiling the graduated bar uses for ``scope``.

        The **minimum** of the local ceiling over the scope and every one of its
        ancestors (``scope_ancestors``), so a parent's ceiling is a hard upper
        bound on the scope beneath it: the bound is transitive, not the root
        alone. The root (``GLOBAL_SCOPE``, or any ancestor with no override)
        contributes ``daily_interrupt_budget``, so this never exceeds the root.
        A flat scope has one ancestor (itself), and a degenerate scope (weight
        1.0, inherited ceiling) collapses to ``daily_interrupt_budget``:
        identical to the prior single-pool denominator.
        """
        return min(self._local_ceiling(a) for a in scope_ancestors(scope))


@dataclass(frozen=True)
class PolicyPack:
    """The single runtime-neutral policy source the kernel reads from.

    Has no behavior of its own beyond supplying policy values + predicates; the
    kernel owns all control flow. Identified by ``name`` + ``version`` (logged
    per decision for audit).
    """

    name: str
    version: str

    # step 1: default empty => keep-all (the kernel keeps every item).
    discard_predicates: Sequence[DiscardPredicate] = ()
    # step 2
    effort_taxonomy: EffortTaxonomy = field(default_factory=EffortTaxonomy)
    # step 3
    convergence: ConvergenceHeuristics = field(default_factory=ConvergenceHeuristics)
    # step 4
    judgment: JudgmentPolicy = field(default_factory=JudgmentPolicy)
    # step 5: default empty validity rules => every question is valid.
    validity_rules: Sequence[ValidityRule] = ()
    ask: AskPolicy = field(default_factory=AskPolicy)
    # step 7
    budget: BudgetKnobs = field(default_factory=BudgetKnobs)
    # Stage 0: trigger-detection hook; defaults to no-op (nothing triggers).
    stage0_trigger: TriggerHook = _no_trigger
