"""Stage 0: input conditioning (pre-loop).

Ships the conditioning interface (``condition``), the typed output (``Item``), a
trivial identity pass-through naive, and a pack-fillable trigger-detection hook
(defaults to no-op). The naive is the simplest correct behavior for this seam.
"""

from __future__ import annotations

from buddhi.stage0.conditioning import Item, RawItem, condition

__all__ = ["Item", "RawItem", "condition"]
