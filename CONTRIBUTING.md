# Contributing to Buddhi

Thank you for taking the time to contribute. Buddhi is a small, pure-standard-library
Python package, and the goal of these notes is to keep contributing to it
predictable: how to set up, how to run the suite, what we expect of a change, and
the one principle that governs what belongs in this repository versus in your own
code.

## Setup

From the repository root, install the package in editable mode with its test
dependency:

```bash
pip install -e ".[test]"
```

The `buddhi` package itself has no runtime dependencies; it is pure standard
library. The only thing the `[test]` extra adds is `pytest`, used to run the suite.

## Running the tests

```bash
python -m pytest tests/ -q
```

Every change is expected to keep the suite green, and new behavior is expected to
come with tests that exercise it. The suite is example-based and parametrized (no
property-based testing framework), so a new test is usually a small, explicit case
that names the behavior it pins. If you change a contract, update the tests that
assert it in the same change rather than in a follow-up.

You can also run the end-to-end demonstration to confirm the kernel imports and
runs against the reference implementation:

```bash
python -m buddhi
```

It prints a short walkthrough and ends with `SMOKE PATH OK`, exiting 0.

## Code style

- PEP 8, with type hints on public functions and on anything non-obvious.
- Pure standard library: do not add a new runtime dependency. If you believe a
  change genuinely needs one, open an issue first and explain why the standard
  library cannot serve.
- Prefer small, readable functions over cleverness. The kernel's value is partly
  that it can be read end to end, so favor code that stays inspectable.

## Issues and pull requests

- Open an issue before a large change so the design can be discussed before code is
  written. Small fixes can go straight to a pull request.
- Keep a pull request focused on one thing. Describe what changed and why, and link
  any related issue.
- Sign off your commits in the DCO style, certifying you have the right to submit
  the work under the project's Apache-2.0 license:

  ```bash
  git commit -s -m "your message"
  ```

  This adds a `Signed-off-by:` line to the commit message.

By participating you agree to abide by our [Code of Conduct](./CODE_OF_CONDUCT.md).
If you find a security issue, please follow the disclosure process in
[SECURITY.md](./SECURITY.md) rather than opening a public issue.

## The uniform contribution norm

This applies to every seam the kernel exposes, and singles out none of them.

The reference implementation ships the **simplest correct behavior** for each
seam: just enough to make the kernel run end to end and to demonstrate the
contract. It is a competent-but-naive baseline, not a production method. Across the
whole reference, the bar is the same for every seam: implement the contract
correctly and minimally, and stop there.

Substantive policy or domain-specific behavior belongs in a consumer's **own**
policy pack or adapter, not upstream in the reference. If you have a richer way to
fill a seam (a smarter selection rule, a real transport, a domain-aware
predicate), that is exactly the kind of thing the seam interface exists to let you
supply from your own code. Compose it on top; do not bake it into the reference.

The reasoning is neutral and structural. The kernel earns its keep by keeping the
reference minimal and inspectable: a clean baseline that a reader can hold in their
head, against stable contracts that do not shift as features accumulate. Richer
behavior is composed by consumers precisely so that the reference stays a baseline
and the seam contracts stay still. Folding domain-specific behavior into the
reference would erode both.

In practice this gives a clean, consistent basis to decline an over-rich
contribution to any seam: not because the idea is unwelcome, but because its home
is a consumer's policy pack or adapter rather than the reference. Contributions
that fix correctness, sharpen a contract, improve clarity, or strengthen the tests
are always welcome upstream.

To see what the seams are and how to fill them for a new domain, read
[docs/extending.md](./docs/extending.md). For the rationale behind the seam
boundaries and the seven decisions, read [docs/decisions.md](./docs/decisions.md).
