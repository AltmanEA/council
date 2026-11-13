"""Adapters for the Documenter Service MVP ports (mvp-contract §1).

Filesystem / stdout implementations. These are the only impure layer; the
core stays deterministic. Every adapter obeys the MVP safety protocol
(mvp-contract §2.1): no writes outside documenter/ state, no git.
"""
