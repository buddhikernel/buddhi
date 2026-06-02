"""Router seam: per-item model/effort selection (interface only).

The router is consumed as a **commodity**: it recommends a model + effort for an
item (and owns provider selection, the budget-aware tier waterfall, and
failover). The kernel never embeds a provider. Step 2 only *binds* the router's
recommendation to the iteration budget and the stream ceiling.

No concrete router ships in the kernel. The reference adapter lives in
``buddhi/reference/naive_pack.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from buddhi.stage0.conditioning import Item


@dataclass(frozen=True)
class RouterPick:
    """A router's recommendation for one item (before the kernel clamps it)."""

    model: str
    effort: str
    rationale: str = ""


@runtime_checkable
class Router(Protocol):
    """Recommend a model/effort for one item. Implemented by an adapter."""

    def recommend(self, item: "Item") -> RouterPick:
        ...
