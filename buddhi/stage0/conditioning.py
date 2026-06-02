"""Stage 0: input conditioning.

Stage 0 is a one-time pre-pass that conditions raw input into the typed items
the seven-step loop consumes (``raw input -> typed items``). It runs **once**,
before the loop, not per iteration.

What the kernel ships:

  1. the conditioning **interface**            -> ``condition(raw, pack)``
  2. the **typed output** type                 -> ``Item`` (what the loop consumes)
  3. a **trivial identity pass-through naive**  -> raw item -> typed item, unchanged
  4. a **trigger-detection hook**              -> pack-fillable, defaults to no-op

The naive conditioning is the simplest correct behavior for this seam, the same
posture as every other seam's reference. It returns its input as typed items
unchanged; the trigger hook is consulted for *detection* and the result is
recorded on the item, but the naive performs no further transformation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence, Tuple

from buddhi.policy import PolicyPack, TriggerHook, _no_trigger


@dataclass(frozen=True)
class RawItem:
    """Raw, pre-conditioning input. Substrate-neutral: a plain payload + metadata."""

    id: str
    payload: str
    # who/what produced this item (used by the step-7 exclusion lattice).
    source: str = "unknown"
    # 0..1 importance of the item (drives the high-stakes bypass + effort).
    stakes: float = 0.0
    # 0..1 how confident the model is it can decide this item on its own (step 4).
    model_confidence: float = 1.0
    # the sequence of change-kinds observed across prior rounds (step 3).
    changes: Tuple[str, ...] = ()
    # arbitrary policy-predicate fodder (e.g. file path, generated-flag).
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Item:
    """The typed item the seven-step loop consumes (Stage 0's typed output).

    Carries everything the decision functions read: all inputs are explicit, so
    no decision ever reaches for ambient state.
    """

    id: str
    payload: str
    source: str = "unknown"
    stakes: float = 0.0
    model_confidence: float = 1.0
    changes: Tuple[str, ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)
    # Stage 0 detection flag: did the trigger hook fire for this item? The naive
    # records it but does not act on it.
    trigger_fired: bool = False

    def with_change(self, kind: str) -> "Item":
        """Return a copy with one more change-kind appended (for loop iteration)."""
        return replace(self, changes=self.changes + (kind,))


def condition(
    raw_items: Sequence[RawItem],
    pack: "PolicyPack | None" = None,
) -> list[Item]:
    """The Stage 0 conditioning interface: trivial identity pass-through naive.

    Maps each raw item to a typed ``Item`` **unchanged** (identity). The trigger
    hook is read from ``pack.stage0_trigger`` (PolicyPack is the single source);
    when no pack is supplied the no-op default is used. The result is recorded on
    ``Item.trigger_fired`` and otherwise ignored.
    """
    trigger: TriggerHook = pack.stage0_trigger if pack is not None else _no_trigger
    typed: list[Item] = []
    for raw in raw_items:
        fired = bool(trigger(raw))  # detection only; the naive does not act on `fired`
        typed.append(
            Item(
                id=raw.id,
                payload=raw.payload,
                source=raw.source,
                stakes=raw.stakes,
                model_confidence=raw.model_confidence,
                changes=raw.changes,
                meta=raw.meta,
                trigger_fired=fired,
            )
        )
    return typed
