# Positioning: why this is not X

Buddhi is small, and several established categories sit close enough that it is
easy to mistake it for one of them. This page draws the boundaries. For each
neighbouring class it states plainly what Buddhi **shares** with that class and
where it **differs**, so the contribution can be read on its substance rather
than on a label.

The one-line frame, used throughout: a runtime *executes* work; Buddhi decides,
per item and across a stream, how much cognition each item deserves, when to
stop, and when a human's judgment is required. It sits above the thing that
does the work, not inside it. The core idea is in [`./concept.md`](./concept.md);
what is proven versus merely asserted is in
[`./claim-and-bound.md`](./claim-and-bound.md); terms are defined in
[`./glossary.md`](./glossary.md).

---

## (a) Agent frameworks and orchestration runtimes

Examples in this class build and run agents: they wire channels in, call tools
and models, and drive a task to completion.

- **Shares.** Both operate over a stream of work and both call models. Buddhi
  is happy to run on top of any such runtime.
- **Differs.** A runtime answers *how* to do the work. Buddhi answers a
  question the runtime does not: *how much* of the cognitive budget this item
  deserves, whether the loop has converged, and whether the disposition belongs
  to the model or to a human. It is the caller, not the callee; it acts on the
  runtime from above, choosing effort tiers and escalation rather than producing
  the work product itself. A runtime that gained these decisions would have
  grown an executive function; that executive function is what Buddhi factors out
  as a separate, runtime-neutral layer.

## (b) Model and cost routers

This class selects, per request, which model and how much inference to spend:
a mature, commoditized capability.

- **Shares.** Buddhi also wants the right model and effort for each item, and it
  uses exactly this capability to get them.
- **Differs.** Buddhi claims **no novelty here**. Per-item model and effort
  selection is a commodity it *consumes* through the Router seam
  (`Router.recommend(item) -> RouterPick(model, effort)`). A router answers
  "which model, how hard"; Buddhi takes that answer and then clamps it to the
  stream's effort ceiling and the iteration budget, and goes on to decide the
  things a router does not touch: convergence, judgment routing, pre-reasoned
  options, and admission against a cognitive budget. The router is one of five
  interchangeable seams Buddhi sits on; it is not the thing Buddhi is.

## (c) Approval gates and human-in-the-loop schedulers

This class pauses an agent to ask a person before a sensitive action, or
schedules tool-call approvals: a binary allow/deny on a specific operation.

- **Shares.** Both can route a decision to a human, and Buddhi can deliver its
  asks through such a mechanism. The EscalationTransport seam
  (`deliver(ask)`) is exactly the right place for an approval channel to plug
  in. Buddhi holds the interface and never a concrete transport.
- **Differs.** A gate decides *whether* one action is permitted; it carries no
  view of how much an item is worth, whether the work has converged, or whether
  the question is even well-formed. Buddhi does the deciding *before* anything
  reaches a human: it routes judgment by confidence, detects convergence,
  rejects malformed asks, and, when escalation is warranted, pre-reasons two
  to four options with one starred recommendation rather than emitting a bare
  yes/no prompt. It also asks whether the question was already resolved out of
  band, through the OOBSource seam, so a human is not interrupted for something
  already handled. A gate is a single late checkpoint; Buddhi is the policy that
  decides which items ever reach one and in what shape.

## (d) Hierarchical reinforcement learning

HRL composes decision-making across temporal scales: high-level options or
sub-goals selecting lower-level policies.

- **Shares.** The nested structure rhymes. Buddhi's closure operator applies the
  same controller at two levels: a parent stream's allocation decision, and then
  the per-item decisions inside a child stream it grants budget to. That is
  decision-making across scales, like an option selecting a sub-policy.
- **Differs.** Buddhi is policy-as-code, not a learned policy. There is no value
  function, no option-value estimate, no training loop. Every decision is an
  explicit, inspectable rule (a confidence threshold, an effort clamp, a
  graduated admission bar) supplied by a single policy source and reproducible
  on a deterministic reference pack. Where HRL learns *when* to switch options
  from reward, Buddhi's switching is written down and auditable line by line.
  The nesting is allocation-recursion (the same function one level up), not a
  hierarchy of trained controllers.

## (e) Blackboard and contract-net architectures

These classic multi-agent designs share a common state (the blackboard) and
allocate work among participants, often by bidding and negotiation (contract
net).

- **Shares.** Buddhi keeps shared state (interrupt counters and a
  source-exclusion lattice behind the Store seam) and is centrally concerned
  with allocating a scarce resource across items.
- **Differs.** There is exactly one operator, and it allocates by recursion
  under a budget. There is no bidding, no announcement-and-award, no negotiation
  among agents. More pointedly, Buddhi has **no coordination layer at all**:
  it does not partition work among children, avoid conflicts between them, or
  lock shared resources. Granting a child stream budget recurses into that
  child's items and nothing more. The case where acting on one item changes
  whether another is worth acting on is deliberately out of scope and belongs to
  a separate coordination layer (see [`./limits.md`](./limits.md)). A blackboard
  system coordinates many agents over shared work; Buddhi rations one budget over
  independent items.

## (f) Control theory and hierarchical scheduling

A controller drives a plant toward a setpoint with feedback; hierarchical
schedulers compose resource budgets across nested levels (a parent budget
bounding its children).

- **Shares.** The resemblance is real and intended. The rising
  required-confidence bar is a pacing mechanism on a binding budget constraint.
  It reads as a shadow price on interrupts, a PID-like feedback term that makes
  admission harder as spend climbs. The line of work on dual mirror descent for
  online allocation (Balseiro, Lu, and Mirrokni, *Dual Mirror Descent for Online
  Allocation Problems*, arXiv:2002.10421 / 2011.10124) formalizes exactly this
  shadow-price-on-a-constraint reading. And the budget composes across levels the
  way nested schedulers do: each scope carries a ceiling that its parent bounds,
  and spend accrues up the tree, so a subtree can never overspend its parent (and
  thus never the root).
- **Differs.** The controlled quantity is a cognitive budget, and the actuators
  are discrete per-item dispositions (discard, converge, model-handle, reject
  as invalid, mark resolved out of band, escalate, deny), including deferral of
  the decision to a human. There is no continuous plant, no analog setpoint, no
  smooth control signal. The bar is also explicitly a *soft* pacing bar, not a
  hard cap: a sufficiently high-stakes or high-confidence item clears it even
  from a saturated budget. The one hard guarantee is narrower and structural: an
  excluded source is checked and denied before the bar is ever consulted, so no
  bypass admits work from an excluded source. The maturity of these claims is
  laid out in [`./claim-and-bound.md`](./claim-and-bound.md).

---

## What is genuinely new, stated narrowly

Stripped of the comparisons, the contribution is small and specific: a single
composable controller that runs unchanged on one item and on a
stream-viewed-as-an-item, rationing a hierarchical cognitive budget through a
graduated admission bar, with judgment routing to a human as a first-class
disposition. The pieces it leans on (model and effort routing, an approval
transport, shared counters) are commodities consumed through seams, claimed
with no novelty. The reduction theorem (the hierarchical budget collapses
exactly to a single shared pool under degenerate settings) and the closure
property (the supervisor literally reuses the controller once per child) are
demonstrated and backed by named tests; see
[`./claim-and-bound.md`](./claim-and-bound.md) for the proven-versus-asserted
split. Scale-invariance across genuinely different substrates is asserted, not
demonstrated. What is exercised here is the kernel on its own reference (naive)
pack, pinned by the property tests, not any concrete application; that limit is
stated plainly.

---

## See also

- [`./concept.md`](./concept.md): the core idea, one controller, the operator
  and budget composition.
- [`./claim-and-bound.md`](./claim-and-bound.md): proven, asserted, and out of
  scope.
- [`./glossary.md`](./glossary.md): terms, including the Simon-lineage
  disambiguation.
- [`../README.md`](../README.md): quickstart and the full doc map.
