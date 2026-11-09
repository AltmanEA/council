<!-- CHANGES v0.4.1: Removed stray `Source:` metadata field from non-RU document per §7.2 compliance fix. -->
<!-- CHANGES 0.5.0: Updated Role Activation Rules to reference scenario-driven assignment with scenario/index.md instead of backlog/index.md. -->
<!-- CHANGES v0.5.2: Clarified deferred fallback in Escalation Resolution Paths — added sentence stating the runtime enforces timeout automatically: when a session is resumed past `timeout_at`, the `fallback_strategy` from `EscalationRecord` is applied without further operator input. Matches execution-runtime enforcement. -->
<!-- CHANGES v0.5.4: Moved from root-level `protocol-core/` to `docs/protocol-core/` as part of documentation separation (sess-documentation-separation). Path update only, no content change. -->
<!-- CHANGES 0.5.3: Added §Outcome-to-Transition table mapping all `ConsensusVerdict.outcome` values to next-phase transitions, escalation reasons, and notes (resolves readiness finding A-06). -->
