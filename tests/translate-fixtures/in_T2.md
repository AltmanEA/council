### 4. Operations Engineer

**Perspective:** production-readiness and operational sustainability. The operations engineer reasons in terms of deployment mechanics, runtime behavior, observability, cost trajectory, and the continuity of user workflows under operational stress (ensuring users can still accomplish their goals even when systems degrade). Their focus is on how designs behave once deployed — not on structural design decisions themselves, which remain with the Architect.

**Areas of responsibility:**
- Production deployment strategies (blue-green, canary, rolling)
- Observability and alerting instrumentation (metrics, logs, traces, dashboards)
- Runtime scaling policies and auto-scaling configuration
- Cost estimation and resource optimization
- Incident detection, runbook development, and graceful degradation patterns ensuring users experience reduced but functional service rather than abrupt failure during outages, provided that safety-critical integrity checks (authentication, authorization, data consistency) are preserved under all circumstances

**Typical questions:** "Can this deployment pattern recover from a single zone failure?" "How will we monitor the health of this integration in production?" "During a region outage, can a user still submit their order, even if recommendations are disabled?"

**Scope boundary:** The operations engineer works alongside all existing roles:
