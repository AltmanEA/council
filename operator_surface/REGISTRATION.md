# Operator Surface Registration Guide

> **Implementation artifact** — not a project document. This file lives under
> `operator_surface/` and is owned by the operator (not the Documenter Service).

---

## 1. Overview

The **Operator Surface** exposes a JSON-RPC stdio server that the operator uses
to submit tasks, run audits, manage sessions, and perform governance actions
(e.g. precheck overrides, escalations).

When the surface starts successfully it:

1. Prints a `READY` line to stdout, and
2. Creates the **readiness sentinel** at `<state_root>/documenter/.operator_surface_ready`
   (empty file, touch semantics).

## 2. How to Register the MCP stdio Server

The operator registers the Operator Surface as an MCP stdio server in their
OpenCode workspace configuration **when they decide**. This plan does not
perform registration automatically — it is the operator's decision.

### 2.1 Launch Command

```bash
python3 -m operator_surface
```

### 2.2 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `COUNCIL_OPERATOR_ID` | yes (for auth) | Operator identifier (used in tokens). |
| `COUNCIL_OPERATOR_SECRET` | yes | HMAC signing secret for token verification. |
| `COUNCIL_STATE_ROOT` | no | Base directory for session state (defaults to current directory). |
| `COUNCIL_TEST_MODE` | no | Set to `1` for test mode (uses stub ports, no real adapters). |
| `COUNCIL_CALLER_CLASS` | no | Auth caller class: `operator` / `agent` / `service` (default: `operator`). |
| `COUNCIL_KNOWN_SERVICES` | no | Comma-separated list of known service identifiers. |
| `PRE_CHECK_TIMEOUT` | no | Pre-check timeout in seconds (default: 5.0). |

### 2.3 Workspace Configuration (example)

Add a tool registration to your workspace config (e.g. `.opencode/opencode.jsonc`):

```json
{
  "mcpServers": {
    "operator-surface": {
      "command": "python3",
      "args": ["-m", "operator_surface"],
      "env": {
        "COUNCIL_OPERATOR_ID": "op-alice",
        "COUNCIL_OPERATOR_SECRET": "<your-secret>",
        "COUNCIL_STATE_ROOT": "<path-to-state-root>"
      }
    }
  }
}
```

## 3. Sentinel Semantics

The readiness sentinel is created at the path defined by the constant
`OPERATOR_SURFACE_SENTINEL` (value: `"documenter/.operator_surface_ready"`)
relative to the state root, **immediately after** the `READY` line is printed.

- **Presence** = the surface has started successfully.
- **Absence** = the surface has not yet started (or started with a sentinel
  creation failure, which is non-fatal — the server still serves requests).

### 3.1 Sentinel is NOT Tier 2+ Activation

The sentinel file is a **readiness indicator** for the Operator Surface itself.
It is **not** a Tier 2+ activation act. Per ADR-013, Tier 2+ activation is
gated by the **documenter_policy.yml** file (active_tier >= 2, briefing_ref
non-null, briefing file present) **plus** the unbuilt Operator Surface as code.
This operator-surface package never modifies `documenter_policy.yml`.

## 4. Rollback

To undo the registration:

1. **Remove** the tool registration from your workspace config (e.g. delete
   the `mcpServers` entry).
2. **(Optional)** Remove the sentinel file:
   ```bash
   rm -f <state_root>/documenter/.operator_surface_ready
   ```

## 5. Important Notice

Registration and activation of the Operator Surface are OPERATOR acts. The
surface never registers itself; it requires explicit configuration by the
operator to become available as an MCP tool.
