# Security Policy

## Reporting a vulnerability

If you discover a security issue in Buddhi, please report it privately by email
to **hello@buddhikernel.com**. Do not open a public issue for security reports.

Please include enough detail to reproduce the issue: the affected version, a
minimal example, and the impact as you understand it. We will acknowledge your
report, keep you informed of progress, and credit you in the fix unless you
prefer to remain anonymous.

## Scope

Buddhi is a pure-standard-library policy kernel: it has no network or filesystem
access of its own and no runtime dependencies. The relevant concerns are
therefore the correctness of the decision logic and the integrity of any policy
pack or adapter a consumer supplies. Substrate-specific transports and resolvers
live in adapters, outside this repository, and should be reported to their own
maintainers.

## Supported versions

Buddhi is pre-1.0 (current version 0.0.0). Fixes are made against the latest
version on the default branch.
