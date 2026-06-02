# Where it breaks

Buddhi is one composable controller that allocates a cognitive budget over
independently evaluable items, and the same controller run one level up over a
stream-viewed-as-an-item. Several things follow from that shape, and they are
limits, not bugs. Each is stated plainly here so an implementor knows the
boundary before they hit it. The mechanism these limits sit on is described in
[the concept doc](./concept.md) and [the budget doc](./budget.md); the maturity
of each claim is tracked in [claim and bound](./claim-and-bound.md).

## L1: Items must be independently evaluable

The controller decides one item at a time. Its disposition for an item is a
function of that item and the budget state; it does not consult the other items
in the stream. That is the source of its compositionality, and also the limit:
**coupled items are out of scope.**

Two items are coupled when acting on one changes whether the other is worth
acting on. Concretely, suppose two reviewer comments propose edits to the same
function:

- Comment A: "extract this branch into a helper."
- Comment B: "add a guard clause to the second half of this branch."

Once A is applied, B may be unnecessary, because the branch it targeted no longer
exists in that form, or it may now be wrong, anchored to a line that has moved.
The kernel evaluates A and B in isolation. It cannot see that applying A
dissolves B, so it will route both, and never notice the two are really one
decision.

This is deliberate. Detecting that one action changes the worth of another
requires reasoning about the joint effect of a set of actions, not the marginal
value of each, and that reasoning belongs to a coordination layer above the
kernel, not inside the per-item loop. The kernel ships no inter-item
coordination, conflict-avoidance, or work-partitioning of any kind; see
[the concept doc](./concept.md) for why that line is drawn where it is.

## L2: Order-dependence within a scope

The admission bar is graduated: `required_confidence` rises with the
interrupts already spent in a scope, from `base` at zero spend toward `cap` at
full spend. Evaluation is sequential. The two facts together mean that **the
same items presented in a different order can escalate a different subset.**

An item evaluated early in a scope faces a low bar; the same item evaluated
after several escalations have already been admitted faces a higher one. So a
marginal item that clears the bar when it arrives first may be denied when it
arrives last, and vice versa. The set of admitted items is a function of arrival
order, not only of the items themselves.

This is the intended behavior of a pacing bar (how the budget spends its
scarcest escalations on what arrives while it still has room), but it is worth
naming, because it means the kernel's output on a fixed multiset of items is not
order-invariant. Two narrow guarantees survive ordering regardless: an item at
or above `high_stakes_threshold` bypasses the bar, and an excluded source is
always denied (the exclusion lattice is checked before the bar). Those, and the
soft-bar boundary in general, are documented in [the budget doc](./budget.md).

## L3: Cross-level budget conservation is opt-in, not automatic

The budget composes across levels by an ancestor clamp plus ancestor accrual: a
scope's `effective_ceiling` is the minimum over the scope and all of its
ancestors, and each admitted interrupt is charged against the scope and every
ancestor up to the root. So a parent's ceiling is a hard upper bound on the total
its subtree can spend through the bar. Conservation across levels (the property
that children of one parent cannot collectively interrupt more than the parent's
ceiling allows) holds **whenever the closure partitions children**, and is proven
by tests (`test_budget_conservation.py`, `test_closure.py`); see
[claim and bound](./claim-and-bound.md) and [the budget doc](./budget.md).

The reference (naive) pack does not partition. It runs the degenerate case: a
single global ceiling (`daily_interrupt_budget = 3`), an empty `scope_allocations`,
and `partition_children = False`. Under those defaults every scope draws from one
shared pool, so there is no subtree partition to conserve. The pack behaves
correctly (it is the prior single-pool behavior exactly), but it does not
*exercise* conservation, because it never partitions.

Two honest caveats remain. First, conservation is a property you opt into by
turning on `partition_children` (and, optionally, setting per-subtree ceilings);
it is a feature of the budget model the kernel enforces, not one the reference
pack demonstrates. Second, the bound is a **bar-gated** one: it governs the
graduated admission bar, not a strict per-period cap. A high-stakes
(`>= high_stakes_threshold`) or `>= cap`-confidence ask still clears any bar and
accrues up the tree, so it can push a subtree past its parent ceiling — the soft-
bar non-guarantee documented in [the budget doc](./budget.md). The reduction from
the hierarchical budget back to the shared pool, and the test that pins it, are
in [the budget doc](./budget.md).

---

These three are where the kernel's claim stops. L1 is a scope decision;
coupling lives one layer up. L2 is a consequence of pacing, named so it is not
mistaken for a defect. L3 is an honest accounting of what conservation the kernel
enforces (a parent bounds its subtree's bar-gated spend, proven by tests), what
you must opt into to get it (partitioning), and the soft-bar bypass that keeps it
from being a strict cap.
