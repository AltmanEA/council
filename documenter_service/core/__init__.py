"""Deterministic pure core: audit, status, policy, registry, trust, errors.

No I/O except through the ports (mvp-contract §1: core is pure functions;
adapters are the only impure layer). core/audit.py and core/status.py import
the tools-layer rule engine as-is; they never fork a rule.
"""
