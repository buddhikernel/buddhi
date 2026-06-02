# The closure

The kernel runs one controller. The closure is what makes that single controller
enough: supervising a stream of work streams is the **same operation** as
supervising the items inside one stream, applied one level up. "How much
cognition to spend on this item" becomes "how much budget to grant this work
stream," and the question is answered by literally the same function.

This is the centerpiece of Buddhi. It is also the one part you can run end to end
today.

## One body, two entry points

There is a single composable controller, `evaluate_item` in
`buddhi/closure.py`. It is pure orchestration over the [seven
decisions](./decisions.md): it takes one typed item and returns a disposition:
one of `DISCARDED`, `CONVERGED`, `MODEL_HANDLED`, `INVALID_ASK`, `RESOLVED_OOB`,
`ESCALATED`, or `DENIED`.

Two functions wrap that body:

- **`supervise_stream`** is the base case. It runs `evaluate_item` over the
  items of one stream, in order, drawing on the shared [cognitive
  budget](./budget.md) when an escalation is admitted.
- **`supervise_stream_of_streams`** is the closure operator. It treats each
  child stream **as an item** (`Stream.as_item()` produces the typed item the
  controller already understands) and runs that item through the *identical*
  `evaluate_item`. The seven decisions, applied to a whole stream, ask whether
  this stream is worth running, how much it should be allowed to spend, and
  whether granting it clears the admission bar. When the parent decision comes
  back `MODEL_HANDLED`, budget has been granted, and the operator recurses into
  that child's items by calling `supervise_stream` on them.

Nothing about the decisions changes between the two levels. What an "item" and a
"stream" mean changes; the allocation logic does not. That is the scale-invariance
the kernel is built around. See [the core idea](./concept.md) for why this
matters and [the component walkthrough](./architecture.md) for where it sits.

## Allocation-recursion only

The closure recurses on **allocation** and nothing else. There is no inter-stream
coordination, no conflict avoidance, no work partitioning, and no locking in the
kernel. The shared `Store` does budget *accounting* across children (that is the
seventh decision, `aggregate_budget`), but it never coordinates the work itself.
Coupled items, where acting on one changes whether another is worth acting on,
are deliberately out of scope; that belongs to a separate coordination layer
(see [where it breaks](./limits.md)).

## Run it

From the repository root:

```
python -m buddhi
```

This runs six demonstrations on the reference (naive) pack and exits 0. The third
demonstration is the closure operator applied to a stream of streams:

```
=== Closure operator — kernel applied to a stream-of-streams ===
  MODEL_HANDLED stream-A-granted        recursed into 2 item(s)
        - MODEL_HANDLED A1
        - CONVERGED     A2
  ESCALATED     stream-B-escalated      no recursion
  DISCARDED     stream-C-discarded      no recursion
```

Read it level by level. Each of the three parent lines is one child stream that
was run through `evaluate_item` **as an item**:

- `stream-A-granted` came back `MODEL_HANDLED`: the parent granted it budget, so
  the operator recursed into its two items via `supervise_stream`, and each of
  those (`A1`, `A2`) is a normal item disposition from the same controller.
- `stream-B-escalated` came back `ESCALATED`: the allocation decision routed the
  stream to a human rather than granting it, so there is no recursion.
- `stream-C-discarded` came back `DISCARDED`: the cheap discard gate rejected
  the stream before any spend, so again no recursion.

The closure does not run the children of a stream it did not grant. Recursion
happens on, and only on, `MODEL_HANDLED`.

## The proof

The claim "the supervisor reuses the identical controller" is not asserted in
prose; it is pinned by two tests in `tests/test_closure.py`:

- `test_closure_literally_reuses_evaluate_item_once_per_child`: the operator
  calls the same `evaluate_item` body exactly once per child stream, with the
  child viewed as an item.
- `test_parent_allocation_is_the_same_function_one_level_up`: the parent's
  allocation decision is the same function as the per-item decision, run one
  level higher.

Run the full suite from the repository root with `python -m pytest tests/ -q`.

The structural scale-invariance (one controller, reused level for level) is
demonstrated and runnable here. Its generality across genuinely different
substrates is a separate question: what is demonstrated here is the kernel on its
reference (naive) pack, pinned by the property tests, not any concrete application.
See [claim and bound](./claim-and-bound.md) for exactly what is proven versus
asserted.

---

Back to [the README](../README.md) · [the core idea](./concept.md) · [the
cognitive budget](./budget.md) · [the architecture](./architecture.md).
