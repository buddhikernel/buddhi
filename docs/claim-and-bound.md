# Claim and bound

This page sorts the work into three honest buckets: what is proven and runnable
today, what is asserted but not yet demonstrated, and what is deliberately out of
scope. It is about evidence and scope only. Where a claim is backed by a test,
the test is named verbatim (`file::name`) so you can run it yourself with
`python -m pytest tests/ -q` from the repository root.

## Proven and runnable today

These are demonstrated by code you can run now, not by argument.

**The closure.** `supervise_stream_of_streams()` does not reimplement the
controller for the parent level. It views each child stream as an item via
`Stream.as_item()` and runs it through the identical `evaluate_item()`:
the same function that runs on a single item. When the parent grants budget
(`MODEL_HANDLED`), it recurses into that child's items. The reuse is literal,
not by resemblance.

* `test_closure.py::test_closure_literally_reuses_evaluate_item_once_per_child`
* `test_closure.py::test_parent_allocation_is_the_same_function_one_level_up`

See [the closure](./closure.md) for the centerpiece walkthrough.

**The invariants.** Each property below is enforced by named tests:

* *Effort ceiling*: no item gets effort above its stream's ceiling; the Router's
  pick is clamped to that ceiling.
  `test_effort_model.py::test_explicit_ceiling_clamps_below_router_pick`;
  `test_policy.py::TestEffortTaxonomyClamp::test_clamp_never_exceeds_ceiling_for_any_level`
* *Monotone admission bar*: within a scope, the required confidence is
  non-decreasing in interrupts spent and bounded in `[base, cap]`.
  `test_aggregate_budget.py::TestRequiredConfidence::test_monotonic_non_decreasing_in_spend`;
  `test_aggregate_budget.py::TestRequiredConfidence::test_bounded_between_base_and_cap`
* *A parent ceiling bounds total subtree spend*: a scope's effective ceiling is
  the minimum over the scope and its ancestors, and each admitted interrupt
  accrues against every ancestor, so a parent ceiling bounds the total marginal
  (bar-gated) spend of its whole subtree: a child cannot spend past an
  intermediate ancestor's ceiling, and siblings cannot collectively exceed their
  parent's ceiling. (The bound is bar-gated; a high-stakes or `>= cap` ask still
  bypasses it; see [the budget doc](./budget.md).)
  `test_budget_conservation.py::TestEffectiveCeilingAncestorClamp::test_effective_ceiling_is_min_over_scope_and_ancestors`;
  `test_budget_conservation.py::TestTransitiveParentBound::test_child_cannot_spend_past_an_intermediate_ancestor_ceiling`;
  `test_budget_conservation.py::TestSiblingSumConservation::test_combined_child_spend_cannot_exceed_parent_ceiling`;
  `test_closure.py::test_parent_ceiling_bounds_the_partitioned_subtree_sum`
* *Termination*: every retry loop terminates. It succeeds within the retry bound
  or re-raises once the bound is exceeded.
  `test_convergence.py::test_succeeds_within_the_retry_bound`;
  `test_convergence.py::test_reraises_once_bound_is_exceeded`
* *Exclusion dominance*: an excluded source is always denied (the lattice is
  checked before the bar), and a permanent exclusion is never lifted by a
  transient retraction.
  `test_aggregate_budget.py::TestExclusionLattice::test_excluded_source_is_denied_before_the_bar`;
  `test_naive_pack.py::TestInMemoryStore::test_transient_retraction_never_crosses_into_permanent`
* *Stage 0 fidelity*: conditioning is 1:1 and payload-preserving; the trigger
  hook flags without rewriting.
  `test_stage0.py::test_condition_is_identity_passthrough`;
  `test_stage0.py::test_trigger_hook_is_detection_only_and_does_not_rewrite`
* *Convergence safety*: a transient failure is never counted as progress or
  convergence; it is a bounded-retry class excluded from convergence accounting.
  `test_convergence.py::test_only_transient_history_is_continue`;
  `test_convergence.py::test_accounted_changes_filters_transient_failures`

**The naive pack and the demo.** The reference pack fills all five seams with the
simplest correct behavior, enough to run end-to-end. `python -m buddhi` runs six
demonstrations on it (Stage 0 conditioning, the seven decisions over one stream,
the closure operator over a stream-of-streams, the two-tier exclusion lattice,
the adapter contract, and the hierarchical budget shared-pool-vs-partitioned),
prints `SMOKE PATH OK`, and exits 0.

**The reduction theorem.** The hierarchical [cognitive budget](./budget.md)
collapses to a single shared global pool with one monotone admission bar under
the degenerate conditions (empty `scope_allocations`, uniform weights, every
ceiling equal to the root budget). This is backed by a differential test that
checks the generalized allocation against an oracle step for step.

* `test_budget_reduction.py::TestReductionToSharedPool::test_generalized_matches_oracle_step_for_step`
* `test_budget_reduction.py::TestDegenerateDefaults::test_every_scope_collapses_to_the_root_budget`

In total, 300 example-based and parametrized tests back these claims (no
property-based fuzzing).

## Asserted but not yet demonstrated

**Scale-invariance beyond one substrate.** The closure operator is
scale-invariant by construction: the same controller runs on an item and on a
stream-viewed-as-an-item, and the tests above show the reuse is literal. That
structural scale-invariance is demonstrated and runnable today.

What is *not* yet demonstrated is generality across genuinely different
substrates. What this repository exercises is the kernel itself: the reference
(naive) pack fills every seam with the simplest correct behavior, and the property
tests above pin the operator, the budget, and the invariants on that pack. The repo
ships and demonstrates the kernel, not a concrete application built on it. The
design deliberately invites a different substrate (different item shapes,
convergence semantics, and escalation channels) to be slotted in behind the same
seams; that is the intended architecture. But whether the kernel composes as
cleanly over such a substrate is an open empirical question, not a settled result
here. The structure invites it; the evidence in this repo does not yet establish
it.

## Deliberately out of scope

**Coordination of coupled items.** The closure is allocation-recursion only:
a parent grants budget to a child and recurses into it. There is no inter-stream
coordination, conflict-avoidance, work-partitioning, or locking in the kernel.
When acting on one item changes whether another is worth acting on, the kernel
does not — and is not meant to — reconcile them. That belongs to a separate
coordination layer above the kernel.

This is a boundary, not a gap to be patched. See
[limits](./limits.md) (L1, coupling) for the full statement, and
[positioning](./positioning.md) for why drawing this line keeps the kernel a
control mechanism rather than a scheduler.

---

See also: [the closure](./closure.md) · [the cognitive budget](./budget.md) ·
[limits](./limits.md) · [positioning](./positioning.md) ·
[back to the README](../README.md).
