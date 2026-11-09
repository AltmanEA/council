# Council
Version: 0.3.2
Status: draft
Last Modified: 2026-11-04
Abstraction: conceptual
changelog-path: CHANGELOGS/project-concept.changes.md

## Purpose

A framework for collaborative decision-making among multiple AI agents when designing systems that combine humans, AI models, and algorithmic software. It is applied during the specification and module- or function-planning stage — defining behavior, interfaces, and implementation approaches without generating code.

The primary output artifact is a structured consensus document that records decisions, open questions, and a risk assessment. All artifacts produced by Council are written in technical English.

---

## Core Principles

1. **Multi-perspective evaluation.** Each design artifact is analyzed independently by different roles before agreement is reached. This prevents the "blind spots" that inevitably arise from a single-perspective view of a task.
2. **Consensus before commitment.** A recommendation is not considered final until all participants converge or the escalation path is triggered. No single agent holds a monopoly on the decision.
3. **Escalation capability.** The system explicitly tracks situations where alignment is impossible and routes such issues to the human operator. Escalation is a normal outcome, not a failure.
4. **Iterative evolution.** Roles, protocols, and escalation rules are updated as the system is used. We start minimal and refine in practice.

---

## Out of Scope

- Software code generation or code analysis
- Code execution or runtime monitoring
- General-purpose chat or conversational AI
- Project management beyond the boundary of a single task

These capabilities may be built on top of Council, but they are not part of its core design.
