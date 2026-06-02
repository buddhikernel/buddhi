# The cognitive budget

The kernel rations cognition at two levels. **Machine cognition, per item**: the
earlier decisions in the loop (see [./decisions.md](./decisions.md)) discard items
not worth acting on, bound which model and how much effort each surviving item may
spend, and stop once an item has converged, so model effort is never spent without
limit. **Human attention, in aggregate**: interrupting a person is the scarcest
resource the kernel rations, so it is metered not per item but across the whole
stream, from a finite account.

This document specifies that second account, the **aggregate cognitive budget**,
and it is exactly the human-interrupt-backed one. Every other decision in the loop
can be made by the model alone; only an escalation spends from this account. The
seventh decision, `aggregate_budget` (`buddhi/decisions/aggregate_budget.py`), is
the admission gate that decides whether a pre-reasoned ask is allowed to spend. It
is one part of a layer whose job is to decide how much of either kind of cognition,
machine or human, any given item deserves.

This document defines the budget exactly as implemented, states the reduction
that recovers the simplest possible behavior, lists the invariants the kernel
guarantees with their backing tests, and then states the one non-guarantee
plainly.

## The shape: a hierarchical weighted allocation

The budget is not a single counter. It is a tree of **scopes**, defined by two
dataclasses in `buddhi/policy.py`:

- `BudgetKnobs` is the root. It carries `daily_interrupt_budget` (the root, or
  default-scope, ceiling), the bar parameters `base` and `cap`, the
  `high_stakes_threshold`, and a `scope_allocations` map of named child scopes.
- `ScopeAllocation` is one scope's local configuration: a `weight` (a local
  scalar on that scope's own ceiling; `1.0` is the identity) and a `ceiling`
  (the scope's absolute interrupt ceiling; `None` inherits the root
  `daily_interrupt_budget`).

A scope key is a path in the tree: a root, then `/`-joined child segments, to
arbitrary depth (the closure builds these with `subtree_scope`, and
`policy.scope_ancestors` recovers a scope's ancestor chain). The ceiling a scope
actually spends against is its **effective ceiling**:

```
effective_ceiling(scope) = min over { scope and its ancestors } of
                           max(1, round(weight_s * ceiling_s))   # each clamped to the root
```

Each scope's own ceiling (its override, else the root budget) is scaled by its
weight and floored at 1; the effective ceiling is then the **minimum of that over
the scope and every one of its ancestors**. That ancestor minimum is what makes
the tree a tree rather than a flat list: a parent's budget is a hard upper bound
on every scope beneath it, so a subtree can subdivide its parent's allowance but
never enlarge it. The root (`daily_interrupt_budget`) is the ancestor of every
scope, so nothing ever exceeds it.

Interrupt accounting accrues up the tree. `aggregate_budget` charges each admitted
interrupt against the scope it is given **and every ancestor up to the root** (via
the Store seam), so an ancestor's count is the total spend of its whole subtree.
The admission bar it computes is the most-binding ancestor's bar: whichever
ancestor is closest to its own ceiling. Sibling scopes never draw down one
another's *own* counter, but they do share their parent's: their combined spend is
bounded by the parent ceiling.

## The graduated admission bar

An escalation is admitted only if its confidence clears a bar that rises as the
scope's budget is consumed. The bar is `required_confidence(spent, budget,
scope)`, a fixed linear ramp from `base` (at zero spend) to `cap` (at full
spend):

```
required_confidence(spent, budget, scope)
    = base + (cap - base) * (spent / max(1, effective_ceiling(scope)))
```

with the ratio clamped to `[0, 1]`. That is the ramp for one scope; the bar a
candidate must actually clear is the **maximum of this ramp over the scope and
its ancestors**, each evaluated at its own accrued (whole-subtree) spend. So a
scope's escalations clear easily early, and a saturated *parent* raises the bar
for every descendant. The bar is pacing, not rationing: it slows spend smoothly
rather than cutting it off at a hard line. The full mental model of why pacing
rather than a hard cap is in [./concept.md](./concept.md).

The rising bar can be read as a shadow price on the binding budget constraint:
each unit of spend raises the price the next ask must "pay" in confidence to be
admitted, the way a dual variable on a resource constraint rises as the resource
tightens. This is the same intuition as dual mirror descent for online
allocation (Balseiro, Lu and Mirrokni, "Dual Mirror Descent for Online
Allocation Problems", arXiv:2002.10421 / 2011.10124), specialized here to a
single fixed linear ramp rather than a learned dual. The way the bound composes
across scopes (a parent ceiling bounding the sum of its children) is the
familiar hierarchical-scheduling arrangement, where each level enforces its own
ceiling and the parent's ceiling bounds the aggregate of its subtree.

## The reduction theorem

The hierarchy is optional. Under three conditions:

1. the tree is depth 1 (no child scope overrides),
2. weights are uniform (every scope keeps `weight = 1.0`), and
3. every ceiling equals the root budget (every `ceiling` inherits
   `daily_interrupt_budget`),

`effective_ceiling(scope)` equals `daily_interrupt_budget` for every scope, so
all scopes share one denominator and one monotone bar. The model is then
**identical** to a single shared global pool with one admission bar: the prior,
pre-hierarchical behavior, exactly. An empty `scope_allocations` map satisfies
all three conditions automatically, because the degenerate `ScopeAllocation()` is
weight `1.0` and an inherited ceiling.

The reference (naive) pack instantiates precisely this degenerate case:
`BudgetKnobs(daily_interrupt_budget=3, base=0.5, cap=0.95,
high_stakes_threshold=0.9)`, no `scope_allocations`, and no child partitioning.
So the simplest correct configuration the kernel ships with is the single shared
pool, and the hierarchy is what you reach for only when you need to fence
distinct scopes off from one another.

The reduction is not asserted; it is tested differentially against an oracle that
walks the shared-pool model step for step:

- `test_budget_reduction.py::TestReductionToSharedPool::test_generalized_matches_oracle_step_for_step`
- `test_budget_reduction.py::TestDegenerateDefaults::test_every_scope_collapses_to_the_root_budget`

## Invariants the kernel guarantees

Each invariant below is backed by a named, runnable test (`python -m pytest
tests/ -q` from the repo root):

- **Effort ceiling**: no item is spent at an effort above its stream's ceiling;
  the budget clamps the Router seam's pick down to that ceiling.
  `test_effort_model.py::test_explicit_ceiling_clamps_below_router_pick`;
  `test_policy.py::TestEffortTaxonomyClamp::test_clamp_never_exceeds_ceiling_for_any_level`.
- **Monotone admission bar**: within a scope the bar is non-decreasing in
  interrupts spent and bounded in `[base, cap]`.
  `test_aggregate_budget.py::TestRequiredConfidence::test_monotonic_non_decreasing_in_spend`;
  `test_aggregate_budget.py::TestRequiredConfidence::test_bounded_between_base_and_cap`.
- **Parent bounds subtree**: a scope's effective ceiling is the minimum over the
  scope and its ancestors, spend accrues against every ancestor, and so a parent
  ceiling bounds the total marginal (bar-gated) spend of its whole subtree: a
  child cannot spend past an intermediate ancestor's ceiling, and siblings cannot
  collectively exceed their parent's ceiling.
  `test_budget_conservation.py::TestEffectiveCeilingAncestorClamp::test_effective_ceiling_is_min_over_scope_and_ancestors`;
  `test_budget_conservation.py::TestTransitiveParentBound::test_child_cannot_spend_past_an_intermediate_ancestor_ceiling`;
  `test_budget_conservation.py::TestSiblingSumConservation::test_combined_child_spend_cannot_exceed_parent_ceiling`;
  `test_closure.py::test_parent_ceiling_bounds_the_partitioned_subtree_sum`.
- **Termination**: every retry loop terminates within its bound and re-raises
  once the bound is exceeded.
  `test_convergence.py::test_succeeds_within_the_retry_bound`;
  `test_convergence.py::test_reraises_once_bound_is_exceeded`.
- **Exclusion dominance**: an excluded source is always denied, and a permanent
  exclusion is never lifted by a transient retraction.
  `test_aggregate_budget.py::TestExclusionLattice::test_excluded_source_is_denied_before_the_bar`;
  `test_naive_pack.py::TestInMemoryStore::test_transient_retraction_never_crosses_into_permanent`.
- **Stage 0 fidelity**: input conditioning is 1:1 and payload-preserving; the
  trigger hook may flag but never rewrites.
  `test_stage0.py::test_condition_is_identity_passthrough`;
  `test_stage0.py::test_trigger_hook_is_detection_only_and_does_not_rewrite`.
- **Convergence safety**: a transient failure is never counted as progress or as
  convergence (transient failures are a bounded-retry class held out of
  convergence accounting).
  `test_convergence.py::test_only_transient_history_is_continue`;
  `test_convergence.py::test_accounted_changes_filters_transient_failures`.

## The one documented non-guarantee

The admission bar is a **soft pacing bar, not a hard interrupt cap**. Two cases
clear any bar, even from a saturated budget:

- an item whose stakes are at or above `high_stakes_threshold` bypasses the bar
  outright, and
- an item whose confidence is at or above `cap` clears the bar by definition,
  since the bar never rises above `cap`.

So a budget that has spent its full effective ceiling can still admit further
escalations. If you need a strict per-period interrupt cap, the kernel does not
give you one, and the conservation limit this implies is set out as L3 in
[./limits.md](./limits.md).

The guarantee that does hold is narrower and exact: **an admitted item's source
is never an excluded one.** The two-tier exclusion lattice (permanent vs.
retractable transient, causes never crossing between tiers) is checked first, before
the bar is even computed. High-stakes items bypass the bar; nothing bypasses the
lattice.

---

See [./concept.md](./concept.md) for where the budget sits in the one composable
controller, [./decisions.md](./decisions.md) for the rationale of
`aggregate_budget` among the seven decisions, [./limits.md](./limits.md) for the
conservation boundary, and [./glossary.md](./glossary.md) for term definitions.
