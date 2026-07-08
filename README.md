# Buddhi

[![PyPI version](https://img.shields.io/pypi/v/buddhikernel.svg)](https://pypi.org/project/buddhikernel/)
[![Python versions](https://img.shields.io/pypi/pyversions/buddhikernel.svg)](https://pypi.org/project/buddhikernel/)
[![CI](https://github.com/buddhikernel/buddhi/actions/workflows/ci.yml/badge.svg)](https://github.com/buddhikernel/buddhi/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20509989.svg)](https://doi.org/10.5281/zenodo.20509989)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Buddhi is the discriminative layer for autonomous agents: it decides when to act, how much effort a task deserves, when to stop, and when a human should decide.**

It is a small, runtime-neutral control kernel. It sits *above* the machinery that already knows how to call models and run tools, and rations a bounded *cognitive budget* — a finite ration of model effort and human interruptions — across a stream of work. It is a control mechanism, not a scheduler or an agent framework: it chooses effort and escalation from above the work and leaves the work itself to the layers around it.

## Why Buddhi

An agent runtime already knows how to invoke models and tools and drive a task to completion. What it usually lacks is a principled way to decide, before and during that work:

- which items deserve attention at all;
- how much model effort each item is worth;
- when further work is unlikely to help;
- when a decision genuinely belongs to a human;
- how to bound total model effort and the number of human interruptions.

Left unmanaged, a supervisor over a stream of agent work fails in three symmetric ways, and all three are expensive:

- **Over-acting** — proceeding on an item that should have been escalated. The damage is silent until someone discovers it.
- **Over-asking** — interrupting a human on something that could have resolved itself. The human becomes the bottleneck, and autonomy is effectively disabled.
- **Over-iterating** — polishing past the point of diminishing returns. Cost accrues with no matching value.

Buddhi is the layer that holds all three in check under a single budget. It treats cognition — machine effort and human attention alike — as the scarce resource, and decides, per item, where that resource is spent or withheld. The framing is Herbert Simon's bounded rationality made explicit and runnable: cognition is a resource an agent allocates for marginal value, rather than an optimum it cannot afford to compute.

## A concrete example: Buddhi Review

The abstraction is easiest to see through a real adapter. [Buddhi Review](https://github.com/buddhikernel/buddhi-review) is a PR review-and-fix loop for Claude Code, built on this kernel. In it:

- each review comment or finding becomes a **work item**;
- the Buddhi kernel decides that item's **disposition** — fix it, ask you, skip it, or defer it;
- the adapter handles the substrate-specific I/O — reading comments from GitHub, calling models, applying fixes;
- the adapter does **not** reimplement the kernel's decision logic; it only carries out the disposition the kernel returns.

PR review is one adapter of the kernel, not the definition of Buddhi. The same controller can sit above other streams of agent work — an issue tracker's comments, a task queue, an agent's inbox — wherever something must decide how much cognition each item deserves and when a human should step in.

## Try it

The kernel is pure standard library, with no runtime dependencies. Clone it and run the demo:

```bash
git clone https://github.com/buddhikernel/buddhi
cd buddhi
python -m pip install -e .
python -m buddhi
```

`python -m buddhi` runs six demonstrations on the reference (naive) pack — Stage 0 conditioning, the seven decisions over one stream, the closure operator over a stream of streams, the two-tier exclusion lattice, the adapter contract, and the hierarchical budget (shared pool vs. partitioned) — one for each part of the design described below. It ends in `SMOKE PATH OK` and exits 0.

To add the test extra and run the suite:

```bash
python -m pip install -e ".[test]"
python -m pytest tests/ -q
```

To depend on the kernel from your own code instead, `pip install buddhikernel` and `import buddhi`.

## How it works

One controller, `evaluate_item()`, runs over each item in turn. For that item it asks seven questions **in order**, and returns the first disposition that ends the item:

1. **Is this worth acting on at all?** A cheap discard gate (default keep-all) drops items that need no cognition, so the budget is never spent on them.
2. **How much model and effort should it get?** The Router (a pluggable model-and-effort picker) proposes a model and effort level; the kernel clamps that pick to the stream's effort ceiling and the iteration budget, so no item can outspend its stream.
3. **Has the work converged?** The stop detector ends the loop once further work yields only diminishing returns. A transient failure is a bounded-retry class, never read as progress.
4. **Should the model decide, or a human?** Governed by a confidence threshold: the model handles what it is confident about and defers the rest as a *business question*.
5. **Is the ask well-formed?** A malformed escalation is rejected; a valid one is pre-reasoned into two to four options with one starred recommendation, so a human answers a structured question rather than a blank prompt.
6. **Was it already resolved out of band?** If another channel already answered, the loop continues without interrupting anyone.
7. **Does the escalation clear the budget's bar?** As interrupts accumulate, the required confidence rises, so marginal asks quietly self-resolve while genuinely high-stakes ones still escalate. An excluded source is denied before the bar is ever consulted.

Each decision lives in its own module and returns one of seven dispositions:

| # | Decision (`module`) | It decides | Disposition |
|---|---|---|---|
| 1 | `worth_acting` | worth acting on at all? | `DISCARDED` |
| 2 | `decide_spend` (`effort_model`) | which model, how much effort (clamped) | annotates; does not end the item |
| 3 | `has_converged` (`convergence`) | has the work converged? | `CONVERGED` |
| 4 | `route_judgment` (`judgment_routing`) | model decides, or defer to a human? | `MODEL_HANDLED` |
| 5 | `validate_and_ask` (`validity_and_ask`) | is the ask well-formed? | `INVALID_ASK` |
| 6 | `check_oob_resolution` (`oob_resolution`) | already resolved out of band? | `RESOLVED_OOB` |
| 7 | `aggregate_budget` | does it clear the budget's bar? | `ESCALATED` / `DENIED` |

The diagram below shows the whole flow: raw input conditioned into typed items, the supervisor that applies the controller to a stream viewed as an item, the seven decisions in order, and the five seams (the kernel's extension interfaces, defined below) that feed them.

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="docs/assets/controller-flow.mobile.dark.svg">
  <source media="(max-width: 600px)" srcset="docs/assets/controller-flow.mobile.svg">
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/controller-flow.dark.svg">
  <img src="docs/assets/controller-flow.svg" alt="The Buddhi controller. Raw input passes through a one-time Stage 0 pre-pass into typed items. A supervisor runs evaluate_item on a stream viewed as an item; when that returns MODEL_HANDLED it grants budget and recurses into the item-level controller — the seven decisions in order: worth_acting, decide_spend, has_converged, route_judgment, validate_and_ask, check_oob_resolution, aggregate_budget. Five seams — PolicyPack, Router, Store, EscalationTransport, OOBSource — and the budget scope feed specific decisions." width="100%">
</picture>

## Composition and nested work

The same controller composes one level up. That is the closure operator, and it is the centerpiece of Buddhi.

- `supervise_stream()` is the base case: it runs `evaluate_item()` over the items of one stream.
- `supervise_stream_of_streams()` views each child stream **as an item** (`Stream.as_item()`) and runs it through the *identical* `evaluate_item()`. "How much cognition to spend on this item" becomes "how much budget to grant this work stream" — the same function, one level up. When a child comes back `MODEL_HANDLED`, the parent has granted it budget, and the operator recurses into that child's own items.

Allocation recurses; nothing else does. The kernel does budget *accounting* across children through the shared Store, but it performs no inter-stream coordination, conflict avoidance, work partitioning, or locking. Coupled items — where acting on one changes whether another is worth acting on — are deliberately out of scope and belong to a separate coordination layer.

The budget it rations is a **hierarchical cognitive budget**: a tree of scopes whose per-subtree ceilings bound total spend, so a parent ceiling bounds the combined spend of its whole subtree. Under degenerate settings it collapses *exactly* to a single shared pool with one admission bar — the simple case you would build if you had never thought about hierarchy — and the reference pack runs precisely that case. The reduction theorem, the invariants, and the conservation tests are in [docs/budget.md](docs/budget.md).

## Architecture and extension points

The kernel is orchestration. Everything domain-specific enters through **five seams** the kernel exposes as interfaces but never implements, plus a one-time Stage 0 pre-pass.

| Seam | Interface | Feeds |
|---|---|---|
| **PolicyPack** | one runtime-neutral policy source: taxonomies, thresholds, phrasings, predicates | every decision, and Stage 0 |
| **Router** | `recommend(item) -> RouterPick(model, effort)` | `decide_spend` |
| **Store** | scope-keyed interrupt counters + a two-tier source-exclusion lattice | `aggregate_budget` |
| **EscalationTransport** | `deliver(ask)` | `validate_and_ask` |
| **OOBSource** | `can_observe_oob() -> bool` | `check_oob_resolution` |

**Stage 0** (`condition()`) is a one-time pre-pass that maps raw input into the typed items the loop consumes. It is *anticipatory* — it shapes the stream so a class of demand never becomes items at all — where the seven decisions are *reactive* and spend the budget. The kernel ships a 1:1 identity pass-through.

No concrete implementation of any seam ships in the kernel. Instead a reference **naive pack** fills each one with the simplest correct behavior: enough to run the demo and the tests end to end, but not a production implementation. That is what `python -m buddhi` exercises. The rationale for why the decisions and seams sit where they do is in [docs/decisions.md](docs/decisions.md).

## Build an adapter

An adapter re-homes the kernel onto a concrete substrate. The adapter contract in `buddhi.adapter` is four verbs over the five seams and the closure orchestration — the adapter supplies substrate I/O, the kernel supplies the decision:

| Verb | Does |
|---|---|
| `ingest()` | yield the substrate's items (an issue tracker's comments, a task queue, an inbox) |
| `run_embedded(item, budget)` | hand one item to the kernel and return its disposition |
| `escalate_async(ask)` | deliver the pre-reasoned ask through the EscalationTransport seam |
| `detect_resolved(item)` | report whether the item was resolved out of band |

To run the kernel on your own domain you fill the five seams and supply a PolicyPack. The worked reference is `buddhi/reference/naive_pack.py` (`NaiveAdapter`), and the step-by-step is in [docs/extending.md](docs/extending.md).

## Status and scope

Buddhi is **alpha** (`0.1.0`); the API may change before `1.0`. What is proven versus asserted is kept honest in [docs/claim-and-bound.md](docs/claim-and-bound.md):

- **Proven and runnable today.** The closure reuse (the supervisor literally reuses the controller once per child), the budget invariants (effort ceiling, monotone admission bar, subtree conservation, termination, exclusion dominance), and the reduction theorem are each pinned by named tests. The reference pack and demo run end to end. The suite is **300 tests**.
- **Asserted, not yet demonstrated.** Generality across genuinely *different* substrates is invited by the design but not yet established here: what this repository exercises is the kernel on its reference pack, not a concrete application built on it. (Structural scale-invariance — the same controller reused unchanged one level up — is itself proven, above.)
- **Deliberately out of scope.** Coordination of coupled items — a boundary, not a gap to be patched. See [docs/limits.md](docs/limits.md), and [docs/positioning.md](docs/positioning.md) for why drawing that line keeps the kernel a control mechanism rather than a scheduler.

## The name

In the Samkhya and Vedanta strands of faculty psychology, *buddhi* is the discriminating intellect — the faculty that judges and decides — as distinct from *manas*, the lower mind that takes in input and throws up impulses. A generative model is manas-like: it generates, associates, and reacts. Buddhi is the faculty placed above it, the one that discriminates what is worth acting on, how much thought a thing deserves, when a matter is resolved, and when to hand it to a human.

## Documentation

**Start here**

- [docs/concept.md](docs/concept.md) — the core idea: one controller, and how the operator and the budget compose.
- [docs/architecture.md](docs/architecture.md) — the nested diagram and a component-by-component walkthrough.

**Go deeper**

- [docs/closure.md](docs/closure.md) — the runnable closure centerpiece (`python -m buddhi`).
- [docs/decisions.md](docs/decisions.md) — the rationale for the seven decisions and five seams.
- [docs/budget.md](docs/budget.md) — the cognitive budget, the reduction theorem, and the invariants.

**Reference**

- [docs/glossary.md](docs/glossary.md) — terms, including the Simon-lineage disambiguation.
- [docs/claim-and-bound.md](docs/claim-and-bound.md) — the maturity ladder: proven, asserted, out of scope.
- [docs/limits.md](docs/limits.md) — where it breaks: coupling, order, conservation.

**Positioning and building on it**

- [docs/positioning.md](docs/positioning.md) — what Buddhi is *not*, and why.
- [docs/extending.md](docs/extending.md) — implementing the seams for a new domain.
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute.

## License and citation

Apache-2.0. See [LICENSE](LICENSE). To cite Buddhi, see [CITATION.cff](CITATION.cff) or the archived release ([DOI](https://doi.org/10.5281/zenodo.20509989)).
