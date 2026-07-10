# The core idea

Buddhi is one composable controller. Given a single item of work, it decides, in order,
whether the item is worth acting on at all, which model and how much effort to spend on it, whether
the work has converged, whether the model may decide or a human's judgment is required, whether
a proposed escalation is well-formed, whether the matter was already resolved out of band, and
finally whether to admit that escalation against a bounded cognitive budget (the seven functions).
That sequence is the function `evaluate_item()` in `buddhi/closure.py`: pure orchestration over
the seven decisions, each living in its own module (their rationale is in [`./decisions.md`](./decisions.md)).

The framing is older than the code. Herbert Simon's bounded rationality treats cognition as a
scarce resource that an agent allocates to maximize marginal value rather than to compute an
optimum it cannot afford. Buddhi makes that allocation explicit and runnable: the *cognitive
budget* is the scarce resource, and the seven decisions are where it is spent or withheld.

Two of the decisions carry the load:

1. **How much effort to spend** is bounded: the Router seam proposes a model and effort level
   per item, and the kernel clamps that pick to the stream's effort ceiling and the iteration
   budget, so no item can outspend its stream.
2. **When a human is required** is governed by a confidence threshold: the model handles what it
   is confident about, and defers the rest as a *business question*: an ask pre-reasoned into two
   to four options with one starred recommendation.

The judgment that decides which is which lives in a PolicyPack, not in the kernel; the kernel
only routes.

## The name and the vision

The name is deliberate. In Samkhya and Vedanta accounts of the mind, *manas* is associated with
deliberation: coordinating inputs and entertaining alternatives. *Buddhi* is the discriminating
intellect associated with determination or ascertainment. *Manas* proposes; *buddhi* decides.

A generative model is *manas*-like: it generates candidate interpretations and actions. Buddhi is
not a further model and produces no additional candidate; it is the determinative layer above the
model, discriminating among the courses the model proposes and deciding what merits action, how
much further effort to allocate, when the matter is settled, and when human judgment is required.
That is the technically meaningful correspondence: the model generates possibilities, and Buddhi
determines what to do with them.

In architectural terms, tools execute, the model generates candidate actions, and Buddhi occupies
the control plane that governs judgment. It allocates a scarce budget of cognition rather than
generating additional candidates.

The implementation is deliberately minimal; the ambition is broader. As agentic systems multiply,
both machine cognition and human attention become scarce, and a principled layer that allocates
both is a missing primitive. Buddhi is a first instantiation of that layer. The design is intended
to generalize across substrates, but that generality remains empirically open. The boundary is
documented in [`./claim-and-bound.md`](./claim-and-bound.md).

## The operator-and-budget composition

The controller described so far operates on a single item. Its composition is what makes the
design interesting at scale, and it has two halves.

### The operator is scale-invariant

`evaluate_item()` runs at *every* level. The base case, `supervise_stream()`, runs the seven
decisions over the items of one stream. The closure operator, `supervise_stream_of_streams()`,
views each child stream **as an item** (`Stream.as_item()`) and runs it through the identical
`evaluate_item()`. "How much cognition to spend on this item" becomes "how much budget to grant
this work stream" — same function, one level up. When the parent admits a child (a
`MODEL_HANDLED` disposition), the operator recurses into that child's items via
`supervise_stream`. There is no second controller for the supervisory level.

This is allocation-recursion only. The kernel does budget *accounting* across children; it does
no inter-stream coordination, conflict avoidance, work partitioning, or locking. Those belong to
a separate coordination layer, deliberately outside the kernel. The scale-invariance is
demonstrated and runnable (the
supervisor literally reuses the controller once per child), and you can watch it happen by
running the demo described in [`./closure.md`](./closure.md).

### The cognitive budget is scale-invariant

The budget is scale-invariant in the same sense the operator is: one allocation rule governs
every level of the tree, not a different mechanism per level. It is a hierarchical weighted
allocation: a tree of scopes, each scope carrying a *weight* (a local scalar on its own ceiling;
1.0 is the identity) and a *ceiling* (an absolute interrupt ceiling, or `None` to inherit the
root budget). A scope's effective ceiling is its weighted ceiling, floored at 1 and taken as the
minimum over the scope and all of its ancestors, so a parent bounds its whole subtree. Spend
accrues up the tree, so a parent ceiling bounds not just each child but the combined spend of its
whole subtree, a conservation property pinned by named tests. Admission rises with spend: the
required confidence climbs linearly from a base (at zero spend) to a cap (at full spend) over the
fraction of the scope's effective ceiling already consumed. Two results make the one-level-up
composition more than an analogy: the conservation property just stated is enforced level for
level, and the whole hierarchy reduces *exactly* to a single shared pool under degenerate
settings (the reduction theorem below). So the budget composing one level up is not a separate
mechanism bolted on: it is the same allocation rule viewed at a different setting. The mechanics,
the conservation tests, and the reduction are in [`./budget.md`](./budget.md).

### The reduction

The hierarchy is not a tax on the simple case, because the simple case is its degenerate point.
Take a depth-1 tree, give every scope uniform weight 1.0, and set every ceiling equal to the
root budget. Then every scope's effective ceiling equals the root budget, and
the whole structure collapses to a *single shared global pool* governed by one monotone
admission bar, exactly the behavior you would build if you had never thought about hierarchy.
The reference pack instantiates precisely this case: one global pool, no per-scope allocations,
children not partitioned. So the generalized budget and the obvious shared pool are the same
object viewed at two settings, and a differential test pins them step-for-step.

## How the pieces fit

The kernel is the orchestration; everything domain-specific enters through five seams ([the
policy source](./architecture.md#the-five-seams), [the Router](./architecture.md#the-five-seams),
[the Store](./architecture.md#the-five-seams), [the escalation transport](./architecture.md#the-five-seams),
and [the out-of-band source](./architecture.md#the-five-seams)),
none of which ship a concrete implementation in the kernel. A reference *naive pack* supplies
the simplest correct fill for each, enough to run the whole thing end to end. The seam contracts
and the reasoning behind each of the seven decisions are in [`./decisions.md`](./decisions.md);
the component diagram and walkthrough are in [`./architecture.md`](./architecture.md); precise
definitions of every term used here, including the Simon-lineage disambiguation, are in
[`./glossary.md`](./glossary.md).

Read next: [`./closure.md`](./closure.md) to run the operator yourself, or
[`./budget.md`](./budget.md) for the cognitive budget and its invariants.
