# Scenarios

Version: 0.1.0
Status: draft
Last Modified: 2026-11-05
Abstraction: protocol
changelog-path: CHANGELOGS/scenario.changes.md

---

## Overview

A **Scenario** defines a set of active Roles and a parameterization of the base five-phase interaction protocol (§Interaction Protocol) for solving problems of a particular kind. It is a declarative recipe, not an execution instance: a Scenario is what gets selected; a Session is what gets created when a Scenario runs against a Task.

Scenarios do not replace or extend the core protocol structure. They select roles, tune parameters, and optionally define preparatory pre-phases that feed input into Phase 1 (Task Submission). Protocol-level modifications (different phase sequences, different consensus logic) are handled by separate protocol variants, not by scenarios.

---

## Model Hierarchy

The conceptual layering is:

| Layer | Concept | Role |
|-------|---------|------|
| Recipe | **Scenario** | Declares roles, parameters, pre-phases |
| Input | **Task** | User-submitted problem description |
| Execution | **Session** | Concrete run combining a Scenario with a Task |
| Participants | **Roles** | Perspective-driven capacities activated by the Scenario |

A Scenario selects Roles from the available set defined in `protocol-core`. A Scenario parametrizes the base protocol (discussion round limits, subject admission criteria, etc.) but does not alter its phase sequence or consensus logic.

---

## Schema

Each Scenario declaration carries the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Human-readable identifier |
| problem_type | string | yes | Free-text description of the problem domain this scenario solves |
| roles | array of role identifiers | yes | Roles to activate; must include Reliability & Security Specialist unless explicitly excluded with documented operator justification |
| pre_phases | array of objects | no | Preparatory steps before Phase 1. Each object has: name, description, max_rounds, output_contract |
| phase_overrides | mapping | no | Per-phase parameter overrides (e.g., max_discussion_rounds, severity_filter). Must not alter structural phase logic |
| version | semantic version string | yes | Independent scenario version |
| composed_of | reserved | no (blocked) | Reserved for future composition support. Validations reject schemas with this field populated at MVP |

---

## Constraints

### Non-negotiable Invariants

1. **Protocol structure immutability.** Scenarios may parameterize the base five-phase protocol but never insert, remove, or reorder phases. The canonical sequence (Task Submission → Individual Review → Discussion Round → Consensus Check → Resolution Formation) is inviolable.

2. **Escalation paths preserved.** No scenario may disable or weaken escalation channels (information gap, irresolvable conflict, risk threshold breach).

3. **Consensus computation unchanged.** The deterministic consensus rules (agree/concerns/blocked-in-scope/blocked-escalation evaluation) cannot be overridden by scenario configuration.

### Safety Guardrails

4. **R&S Specialist inclusion.** The Reliability & Security Specialist role must be present in every scenario by default. Explicit exclusion requires a human-approved reason stored in the session record and a documented justification in Phase 1.

5. **Fixed catalog at launch.** Scenarios are authored exclusively by framework maintainers. Operator authoring is deferred until a governance model exists.

6. **No composability at MVP.** Scenarios reference other scenarios via a reserved field but cannot compose others at launch. Composition validation semantics will be defined in a later milestone.

---

## Relationships

- **Scenario vs Task:** A Task describes *what* needs solving. A Scenario describes *how* the system approaches that type of problem structurally.
- **Scenario vs Session:** A Scenario is a template/recommendation; a Session is a concrete execution instance with a single Scenario bound to a single Task.
- **Scenario vs Roles:** A Scenario selects Roles from the available set. It does not redefine them or their responsibilities. Prompt customization within a Scenario is scoped to emphasis/context injection, not behavioral substitution.
- **Scenario vs Protocol Core:** A Scenario inherits the base five-phase protocol structure from `protocol-core/index.md` and parameterizes it. New protocol variants would be separate artifacts referenced independently.
- **Scenario vs Role Activation Tiers:** The tier model (Core / Extended) in `protocol-core` (§Role Activation Rules) serves as the fallback/default mechanism. Scenarios provide declarative overlays that replace manual justification once fully adopted. Until then, tier-based defaults apply when no Scenario is specified.

---

## Example Scenarios (Illustrative)

These scenarios are proposed as illustrative examples. They are NOT part of the initial implementation — the initial implementation consists of documenting the Scenario abstraction itself. Future iterations will populate a curated catalog based on observed usage patterns.

- **Brainstorming** — Multi-perspective ideation session focused on generating options without premature convergence. Likely includes extended discussion rounds.
- **Grill** — Intense adversarial clarification mode. Multi-round questioning to surface hidden assumptions and requirements before formal review begins. May use higher pre-phase round limits and stricter critical-justification thresholds.
- **Specification Generation** — Transforms a detailed task description into a structured specification. Minimal pre-phases, possibly zero discussion rounds for well-defined inputs.
- **Implementation Planning** — Converts a specification into a step-by-step execution plan. Activates Roles that cover architectural decomposition, operational concerns, and sequencing dependencies.

---

## Compliance Notes

- This document complies with §7 line limit (≤200 lines excluding metadata and changelog entries).
- Russian translation (`index-RU.md`) alignment follows §3.3 translation workflow.
- Version bumps follow §7 conventions: patch for typos/formatting, minor (X.**Y**.Z) for structural additions, major (**X**.Y.Z) for foundational changes.
