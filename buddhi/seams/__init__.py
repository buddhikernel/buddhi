"""The five seam interfaces. No concrete implementation of any seam ships here.

  PolicyPack         -> the single runtime-neutral policy source (policy.py)
  Router             -> per-item model/effort selection
  Store              -> budget counters + two-tier exclusion lattice
  EscalationTransport-> delivery of the pre-reasoned ask
  OOBSource          -> the can-observe-OOB declaration

Reference adapters that fill these seams live in ``buddhi/reference/naive_pack.py``.
"""

from __future__ import annotations

from buddhi.seams.escalation import EscalationTransport
from buddhi.seams.oob_source import OOBSource
from buddhi.seams.policy_pack import PolicyPack
from buddhi.seams.router import Router, RouterPick
from buddhi.seams.store import Store

__all__ = [
    "PolicyPack",
    "Router",
    "RouterPick",
    "Store",
    "EscalationTransport",
    "OOBSource",
]
