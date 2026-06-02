# Decisions and seams: the rationale

This page records *why* the controller decomposes into exactly seven decisions and
why exactly five seams sit where they do. It is rationale, not enumeration: each
decision exists to close a specific failure mode, and each seam sits at the one
boundary where its concern actually lives. The mechanical walkthrough is in
[`./architecture.md`](./architecture.md); the budget mathematics is in
[`./budget.md`](./budget.md); the boundaries of the whole design are in
[`./limits.md`](./limits.md).

## The three failure modes

A supervisor over a stream of agent work can fail in three symmetric ways, and all
three are expensive:

- **Over-acting**: proceeding on an item that should have been escalated. The
  damage is silent until someone discovers it.
- **Over-asking**: interrupting a human on an item that could have self-resolved.
  The human becomes the bottleneck, and autonomy is effectively disabled.
- **Over-iterating**: continuing to polish past the point of diminishing returns.
  Cost accrues with no corresponding value.

The seven decisions are the smallest set that addresses all three without leaving a
gap. Each one is a separable decision because it answers a different question and
fails differently when omitted.

## Why these seven decisions

The decisions run in order; each narrows what reaches the next.

1. **`worth_acting`**: a cheap rule-based discard gate. It removes items that need
   no cognition at all, so the budget is never spent on them. Without it, the
   downstream decisions pay model cost to reach a trivial verdict. The default is
   keep-all, so the gate adds nothing until a policy pack defines a discard rule.

2. **`decide_spend` / `effort_model`**: how much model and effort to spend. This is
   the first guard against **over-iterating**: it clamps the per-item model and
   effort pick to the stream's effort ceiling and to the iteration budget, so no
   single item can spend without bound. The pick itself comes from the Router seam;
   this decision binds that pick to the stream's limits.

3. **`has_converged` / `convergence`**: the stop detector, and the primary guard
   against **over-iterating**. It recognizes when further work yields only
   diminishing returns and ends the loop. A transient failure (a timed-out or errored
   attempt) is treated as a distinct, bounded-retry class and is excluded from
   convergence accounting. Conflating the two would itself be a failure mode:
   reading a transient error as "done" stops too early, and reading it as a result
   escalates too eagerly with the iteration budget untouched.

4. **`route_judgment` / `judgment_routing`**: the model decides, or the item defers
   to a human as a business question, governed by a confidence threshold. This is the
   pivot between **over-acting** and **over-asking**: route too freely to the model
   and you over-act; route too freely to the human and you over-ask. The threshold is
   a policy-pack parameter, not a kernel constant, because the right line differs by
   domain.

5. **`validate_and_ask` / `validity_and_ask`**: the second guard against
   **over-asking**. Before any human is interrupted, the ask is checked for validity;
   a malformed ask is rejected outright. A valid ask is pre-reasoned into 2–4 concrete
   options with one starred recommendation and an escalation confidence, so the human
   answers a structured question rather than starting from a blank page. Routing to a
   human is necessary but not sufficient: a poorly-formed interruption is still an
   interruption that wastes the scarcest resource.

6. **`check_oob_resolution` / `oob_resolution`**: was this already resolved out of
   band? The third guard against **over-asking**. If the question was answered through
   another channel, the loop continues without redoing the work or interrupting again.

7. **`aggregate_budget`**: admit or deny the escalation against the scope's graduated
   admission bar and the two-tier source-exclusion lattice. This is the stream-level
   guard against **over-asking**: as interrupts accumulate, the required confidence
   rises, so marginal items quietly self-resolve while genuinely high-stakes items
   still escalate even from a saturated budget. The lattice is checked first, before
   the bar; an excluded source is denied unconditionally. The budget mathematics, the
   soft-bar non-guarantee, and the reduction to a single shared pool are in
   [`./budget.md`](./budget.md).

Decisions 4 through 7 form a deliberate funnel: should a human decide, is the ask
well-formed, has it already been answered, and can the budget afford it. Collapsing
any pair would lose a distinct check. The order matters: the cheapest and most
decisive filters run first, so cost is spent only on items that survive them.

## Why Stage 0 is a distinct stage, not an eighth decision

Stage 0 is a one-time pre-pass that maps raw input to the typed items the loop
consumes. It runs once, before the loop, and is kept separate from the seven
decisions on purpose. The distinction is temporal and economic:

- The seven decisions are **reactive**: an item exists, work has begun, and the
  controller *disposes* of the item. They **spend** the cognitive budget.
- Stage 0 is **anticipatory**: no item exists yet. It shapes the stream so that a
  class of demand never becomes items at all. It **reduces demand** on the budget
  before allocation begins.

Folding Stage 0 into the loop would collapse a real boundary, the one between
admission control and scheduling. The scheduler disposes of admitted work; admission
control decides what the scheduler ever sees. It would also mis-attribute the value:
the seven decisions allocate a fixed budget across items, while Stage 0's value is
removing items from that allocation in the first place. The kernel ships a 1:1
identity pass-through for Stage 0 (each raw item becomes a typed item unchanged),
plus a pack-supplied trigger-detection hook that defaults to a no-op. The hook may
flag an item; the naive records the flag and does not alter the payload. The kernel
publishes the stage's interface and the simplest correct fill; the domain content
belongs to a policy pack.

## Why the five seams sit where they do

A seam is a boundary where the kernel exposes an interface and ships no concrete
implementation. Each seam sits at the one place its concern actually lives, so the
kernel stays runtime-neutral and pure.

- **PolicyPack**: the single runtime-neutral policy source. Taxonomies, thresholds,
  phrasings, and predicates are all judgment that differs by domain; concentrating
  them in one seam means the kernel encodes mechanism only and never a domain opinion.
  One source, consulted at each decision and at Stage 0, keeps a fleet of
  heterogeneous agents resolving the same latent decision the same way.

- **Router**: `Router.recommend(item) -> RouterPick(model, effort)`. Per-item model
  and effort selection is a mature, commoditized capability, so the kernel consumes it
  as a commodity rather than reinventing it; it claims no novelty here. The Router
  proposes; `decide_spend` clamps that proposal to the stream's ceiling and the
  iteration budget. Placing selection behind a seam keeps the binding decision in the
  kernel and the selection mechanism replaceable.

- **Store**: interrupt counters keyed by scope, plus the two-tier source-exclusion
  lattice. Both are stateful, and the kernel is a pure decision function, so all
  persistence lives behind this one interface. The lattice keeps permanent caps and
  retractable transient exclusions strictly apart so a cause in one tier can never
  silently lift a cause in the other.

- **EscalationTransport**: `deliver(ask)`. The kernel pre-reasons the ask and then
  hands it to a transport it holds only as an interface, never as a concrete channel.
  Decoupling the rich, structured ask from the delivery mechanism keeps the
  pre-reasoned options intact regardless of how a substrate happens to reach a human.

- **OOBSource**: `can_observe_oob() -> bool`. Whether a substrate can ever observe an
  out-of-band resolution is a property of the substrate, not the policy, so the kernel
  asks the substrate to declare it. The kernel then never blocks on a channel the
  substrate has said it cannot observe. Its naive declares it cannot observe, so the
  out-of-band check stays pending, the simplest correct behavior for a substrate that
  makes no such promise.

Every seam ships the simplest correct fill in the reference pack and nothing more.
The reference pack is enough to run end-to-end, not a production method; implementing
any seam for a real domain is the subject of [`./extending.md`](./extending.md).

## What is deliberately not here

Coordination of coupled items (where acting on one item changes whether another is
worth acting on) is not one of these decisions and not one of these seams. The
controller allocates the budget across items and recurses into child streams when one
is granted budget; it never coordinates between items. That concern belongs to a
separate layer. Its boundary, and the other places this design stops, are in
[`./limits.md`](./limits.md).
