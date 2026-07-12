# Glossary

Terms used across the Buddhi documentation, defined once here. For the idea
these terms compose into, see [the concept](./concept.md); for the resource
they allocate, see [the cognitive budget](./budget.md).

## Cognitive budget

The resource Buddhi allocates: a bounded supply of judgment effort and
human-interrupt capacity, spent where its marginal value is highest. It is a
tree of scopes, each carrying a weight and a ceiling. Throughout these docs the
resource being allocated is *always* called the cognitive budget.

## Composable controller / kernel

The mechanism. One pure orchestration function, `evaluate_item()` in
`buddhi/closure.py`, that runs the seven decisions over a typed item. "Kernel"
refers to the same function and the small surface around it; both names denote
the mechanism, never the resource.

## Item

The typed unit the controller evaluates. Each item carries the payload and the
context the seven decisions read. A whole stream can also be viewed as a single
item (`Stream.as_item()`), which is what makes the closure possible.

## Stream

An ordered sequence of items the controller supervises. The base case,
`supervise_stream()`, runs the seven decisions over the items of one stream.

## The closure

The closure operator, `supervise_stream_of_streams()`: it views each child
stream as an item, runs it through the identical `evaluate_item()`, and, when
the parent grants budget, recurses into that child's items via
`supervise_stream()`. This is allocation-recursion only; the kernel has no
inter-stream coordination, conflict-avoidance, work-partitioning, or locking.
See [the closure centerpiece](./closure.md).

## Scope

A node in the budget tree. A scope key is a `/`-joined path (root, then child
segments, arbitrary depth); each scope carries a weight and a ceiling and bounds
its own subtree's interrupt spending. A parent scope bounds its children: a
child's effective ceiling is clamped to its ancestors', and spend accrues up the
path, so a parent ceiling bounds its whole subtree's total.

## Weight

A local scalar on a scope's own ceiling; `1.0` is the identity (no change).

## Ceiling

A scope's absolute interrupt ceiling. `None` inherits the root budget's
`daily_interrupt_budget`.

## Effective ceiling

`effective_ceiling(scope)`: the scope's weighted ceiling, floored at 1, taken as
the minimum over the scope and all of its ancestors, so a parent always bounds
its subtree, and nothing exceeds the root `daily_interrupt_budget`. With an empty
scope-allocations map this equals `daily_interrupt_budget` for every scope. See
[the reduction](./budget.md).

## The graduated admission bar

The required-confidence bar, `required_confidence(spent, budget, scope)`, that an
escalation must clear to be admitted. Within a scope it rises linearly from
`base` (zero spend) to `cap` (full spend) over the fraction
`spent / effective_ceiling(scope)`; the bar a candidate must clear is the maximum
of that ramp over the scope and its ancestors, so a saturated parent raises it.
It is a soft pacing bar, not a hard interrupt cap.

## Base / cap

The two endpoints of the graduated admission bar: `base` is the required
confidence at zero spend, `cap` the required confidence at full spend. The bar
is non-decreasing in spend and stays within `[base, cap]`.

## High-stakes bypass

An item whose stakes are at or above the high-stakes threshold is admitted even
from a saturated budget, bypassing the admission bar (an item whose confidence
is at or above `cap` also clears any bar). The bypass is of the bar only: a
high-stakes item is never exempt from the exclusion lattice.

## The exclusion lattice

A two-tier source-exclusion structure in the Store, checked before the admission
bar. An admitted item's source is never an excluded one; this is the kernel's
narrow true guarantee, distinct from the soft pacing bar.

- **Permanent tier**: a permanent exclusion is never lifted by a transient
  retraction.
- **Transient tier**: a retractable exclusion; retracting it admits sources
  again. Causes never cross between the two tiers.

## Seam

One of the five interfaces the kernel exposes. The kernel holds only the
interface; no concrete implementation of any seam ships in the kernel. The five
are PolicyPack, Router, Store, EscalationTransport, and OOBSource. See
[implementing the seams](./extending.md).

## Policy pack

The single runtime-neutral policy source (`PolicyPack`, `buddhi/policy.py`). It
supplies the judgment (taxonomies, thresholds, phrasings, predicates) at each
decision and at Stage 0.

## Adapter

The component that binds the kernel to a concrete substrate: it conditions raw
input into typed items, runs the controller, and carries asks out through the
transport. The reference adapter is `NaiveAdapter` in the naive pack.

## Stage 0 conditioning

A one-time pre-pass, `condition()` in `buddhi/stage0/conditioning.py`, run once
before the loop to map raw input to the typed items the loop consumes. The
kernel ships a 1:1 identity pass-through (each raw item becomes a typed item
unchanged) plus a pack-supplied trigger-detection hook that defaults to a no-op:
it may flag an item, but the naive records the flag and does not transform the
payload.

## Business question

The disposition where the controller defers a judgment to a human rather than
deciding it itself. Whether a judgment is routed to the model or to a human is
governed by a confidence threshold in `route_judgment`.

## Pre-reasoned ask

The escalation an admitted business question carries to a human:
`validate_and_ask` rejects malformed asks, and otherwise pre-reasons 2-4 options
with one starred recommendation plus an escalation confidence, so the human
chooses among framed options rather than starting cold.

## Convergence

The stop condition detected by `has_converged`: the point at which further
iteration on an item yields no accounted progress. Transient failures are
excluded from convergence accounting (see below).

## Transient-failure class

A bounded-retry class of failures held separate from convergence accounting: a
transient failure is never counted as progress or as convergence, and every
retry loop terminates within its bound.

## Out-of-band resolution

A terminal outcome (`RESOLVED_OOB`) returned when an adapter-supplied check
reports that an item was already resolved externally, before the controller
escalates it. The OOBSource seam declares, via `can_observe_oob()`, whether the
substrate supports such a check; the kernel does not define how the result is
obtained, and the reference implementation always remains pending.

## Attention

Buddhi descends from the economics-of-attention lineage, Herbert Simon's view
of cognition as a scarce resource allocated to maximize marginal value. That
historical sense is the *only* sense in which the word "attention" is used in
these docs. It is unrelated to the "attention mechanism" of transformer neural
networks, which is a different concept entirely. Throughout these docs the
resource being allocated is called the **cognitive budget**; "attention" appears
only in this lineage sense.

---

Back to the [README](../README.md).
