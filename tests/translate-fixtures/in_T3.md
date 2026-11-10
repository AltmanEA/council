The following table maps each `ConsensusVerdict.outcome` value to its next state transition and escalation reason (if applicable). This is the canonical reference for outcome routing.

| `ConsensusVerdict.outcome` | Next phase / state | Escalation reason | Notes |
|----------------------------|-------------------|-------------------|-------|
| `consensus` | Phase 5 (Resolution Formation) | — | All participants agreed. Proceed to artifact production. |
| `conditional` | Phase 5 (Resolution Formation) | — | Concerns present but nothing blocks. Record reservations and proceed. |
| `no-consensus` | Phase 3 (re-enter discussion round) | — | Budget has not been exhausted; additional discussion rounds may resolve the issue. |
| `blocked-escalation` | `awaiting-operator` | `information-gap` \| `irresolvable-conflict` \| `risk-threshold-breach` | Escalation protocol triggered. See §Escalation Protocol below. |

Where:
- `no-consensus` applies when `no_consensus` budget remains (phase_state transitions 4→3 per runtime contract).
- When budget is exhausted, the effective outcome is equivalent to `blocked-escalation` with `reason = information-gap`.
- Missing Core role or invalid-format status also routes to `blocked-escalation` with the appropriate reason, checked independently of this table.
