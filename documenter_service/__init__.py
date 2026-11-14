"""Documenter Service MVP scaffold (Tier 0-1, read-only).

Stage 4 scaffold of the Council Documenter Service per
`docs/en/documenter-service/mvp-contract.md`, `mvp-interfaces.md` and
`mvp-data-models.md`. Operational surface: `audit()`, `delegate(preview: true)`,
`documenter.status()`. The write branch of `delegate()`, `documenter.approve`,
`override_gate` and the Multi-file Commit Protocol are implemented in the
build but POLICY-GATED and DORMANT behind the dual interlock: the Tier 0/1
policy gate plus the unbuilt Operator Surface (ADR-013) — every non-preview
call fails closed with `tier_interlock` (mvp-contract §MVP boundary).

Rule coverage (AGENTS.md §8): audit() REUSES `tools/check_all.scan` and
`tools/docmeta.validate` as-is and therefore covers exactly the deterministic
rules 1, 2, 4, 6 plus naming/schema checks. Rules 3 (glossary terms) and 5
(abstraction consistency) are skill/AI-reserved judgments and are NOT
implemented here in any form; coverage of "rules 1-6" is never claimed.

Dependency policy (mvp-contract §1): Python 3.11+, stdlib + PyYAML (safe_load
via tools/docmeta) only. No process spawning, no model clients, no network
libraries. The read-only operational surface mutates only
`documenter/audit_registry.jsonl` (append) and the `documenter/` state
directory; the dormant Tier 2+ write branch additionally touches staging,
intent and lock files under the operational contract (mvp-contract §2.2).
"""
from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0-scaffold"
