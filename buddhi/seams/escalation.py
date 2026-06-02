"""Escalation transport seam: delivery of the pre-reasoned ask (interface only).

Step 5 *computes* the ask; this seam *delivers* it. The kernel holds **only**
the interface. Every concrete transport is an adapter and is explicitly out of
the kernel: not a chat transport, not a file-based answer channel, not terminal
ergonomics.

No concrete transport ships in the kernel. A recording reference adapter lives
in ``buddhi/reference/naive_pack.py`` for the smoke path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from buddhi.decisions.validity_and_ask import PreReasonedAsk


@runtime_checkable
class EscalationTransport(Protocol):
    """Deliver a pre-reasoned ask to a human. Implemented by an adapter."""

    def deliver(self, ask: "PreReasonedAsk") -> None:
        ...
