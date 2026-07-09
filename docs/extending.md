# Implement the seams for a new domain

To run the kernel on your own domain you fill its five seams: a policy pack,
plus the four object seams (Router, Store, EscalationTransport, OOBSource). No
concrete seam ships in the kernel; the runnable fills live in
`buddhi/reference/naive_pack.py`, and that is the worked reference to copy. Each
fill is a small object with one or two methods; the kernel orchestrates them.

See [`./architecture.md`](./architecture.md) for how the pieces fit and
[`./decisions.md`](./decisions.md) for why each seam is shaped this way.

## The policy pack

`PolicyPack` is the single runtime-neutral source of judgment: your discard
predicates, the effort taxonomy and its ceiling, convergence kinds, the judgment
confidence threshold, validity rules, ask phrasings, and the `BudgetKnobs`.
Start from `naive_policy_pack()` and replace its values with yours:

```python
def my_policy_pack() -> PolicyPack:
    return PolicyPack(
        name="my-domain", version="1",
        discard_predicates=(my_out_of_scope,),
        effort_taxonomy=EffortTaxonomy(
            levels=("low", "medium", "high"), ceiling="high",
            model_by_effort={"low": "...", "medium": "...", "high": "..."}),
        convergence=ConvergenceHeuristics(),
        judgment=JudgmentPolicy(business_question_threshold=0.6),
        validity_rules=(my_ask_has_payload,),
        ask=AskPolicy(option_phrasings=(...), recommended_index=0,
                      min_options=2, max_options=4),
        budget=BudgetKnobs(daily_interrupt_budget=3, base=0.5,
                           cap=0.95, high_stakes_threshold=0.9),
    )
```

## The four object seams

- **Router**: `recommend(item) -> RouterPick(model, effort)`. Picks a model and
  effort per item; the kernel clamps the effort to the stream ceiling and the
  iteration budget. `NaiveRouter` derives effort from the item's stakes.
- **Store**: interrupt counters keyed by scope plus the two-tier exclusion
  lattice (`is_excluded`, `exclude_permanent`, `exclude_transient`,
  `retract_transient`). `InMemoryStore` keeps these in dicts and sets; a
  retraction touches only the transient tier, so causes never cross.
- **EscalationTransport**: `deliver(ask)`. Your real channel (a message, a
  file, a CLI prompt). `RecordingEscalation` just records the asks it receives.
- **OOBSource**: `can_observe_oob() -> bool`. Declares whether your substrate
  can ever observe an out-of-band resolution. `NoOOBSource` returns `False`.

## Stage 0 conditioning

`condition(raw, pack)` is the one-time pre-pass that turns your raw inputs into
the typed `Item`s the loop consumes. The shipped naive is a 1:1 identity
pass-through, usable as-is; a pack-supplied trigger hook may flag an item, and
defaults to a no-op.

## Wiring it end to end

Condition once, then run each item through the composable controller, exactly
what `NaiveAdapter.run_embedded` does:

```python
pack = my_policy_pack()
typed = condition([raw], pack=pack)[0]
result = evaluate_item(item=typed, pack=pack, router=my_router,
                       store=my_store, escalation=my_escalation,
                       oob_source=my_oob, budget=budget)
```

To supervise a whole stream, condition its items and pass them to
`supervise_stream(...)`; the same controller runs over a stream-of-streams via
the closure operator. From the repository root, `python -m buddhi` exercises all
of this on the naive pack.

Back to the [project overview](../README.md).
