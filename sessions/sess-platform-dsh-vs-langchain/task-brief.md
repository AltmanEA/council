# Task Brief — Платформа реализации Консилиума и Документатора

Session: sess-platform-dsh-vs-langchain
Date: 2026-11-18
Mode: fallback (OpenCode subagents), roster: 4 базовые роли, сложность: medium → 1 раунд обсуждения.

## Session Goal

Определить целевую платформу/харнесс для реализации кодового Консилиума (Moderator + role agents) и Документатора: (A) DeepSeek Harness (`dsh`) или (B) текущий запланированный стек Python + LangChain/LangGraph — без оглядки на ранее принятые решения (ADR, project-reference считаются пересматриваемыми).

## Focus Areas

- Детерминизм оркестрации: фазы и переходы вычисляются кодом из структурированных артефактов (statuses, stances, hashes), а не LLM.
- Пригодность каждой платформы как оркестратора (не чата): headless/programmatic invocation, изоляция ролей, limits.
- Стоимость миграции для УЖЕ реализованного Python-кода (Documenter Tier 0–1, Operator Surface, tools, ~1000 тестов).
- Безопасность и аудиторность: fail-closed реестр, approval-hash верификация, developer-preview статус dsh без security audit.
- Зрелость и риск экосистемы: LangChain (зрелый, но тяжёлый/нестабильный API) vs dsh (developer preview, «THERE WILL BE COMPATIBILITY-BREAKING CHANGES»).

## Subject List

- `SUBJ-001`: Платформа оркестрации Консилиума (Moderator + role agents) — dsh vs LangGraph vs иной вариант.
- `SUBJ-002`: Рантайм Документатора (service + operator surface) — оставаться на чистом Python или мигрировать на dsh-плагины.
- `SUBJ-003`: Стоимость и риск миграции существующей Python-реализации при выборе dsh.
- `SUBJ-004`: Соответствие протокольным требованиям безопасности/аудита (fail-closed, canonical hash, approval binding, Layer 0 stack-neutrality).
- `SUBJ-005`: Долгосрочный риск платформы (vendor/preview/API churn, langchain-vs-langgraph дробление, dsh breaking changes, лицензия MIT vs LangChain MIT).

## Questionnaire per Role

**Architect:**
- Q1: Является ли dsh оркестратором рабочего процесса с детерминированными переходами, или это харнесс интерактивного агента (как OpenCode/Koda) — и что из этого нужно протоколу?
- Q2: Где проходит правильная граница: код считает переходы, LLM даёт содержимое — какая платформа этой границе соответствует?

**Reliability & Security Specialist:**
- Q1: Каковы отказные режимы dsh developer-preview (breaking changes, отсутствие security audit, plugin-произвол) применительно к fail-closed реестру и approval-hash гейтам?
- Q2: Какие отказные режимы LangChain/LangGraph (API churn, абстракции скрывающие промпты/ретраи) критичны для аудита?

**Human-Centric Designer:**
- Q1: Что оператору понятнее обслуживать: Python-CLI/JSON-RPC стек или Cordis-плагин-дерево с профилями/патчами?
- Q2: Как выбор платформы влияет на наблюдаемость решений ролей (сырые envelope'ы, диффы для approval)?

**Operations Engineer:**
- Q1: Стоимость эксплуатации: рантаймы (Node vs Python), зависимости, установка, версия-локи, CI для 1000+ тестов.
- Q2: Реалист ли перенос Documenter/Operator Surface на dsh-плагины и каков промежуточный путь при положительном решении?

## Output Limits

- Максимум находок на роль: 5–7; рекомендаций: 3–5; открытых вопросов: 2–3; всего ~150 строк.

## Expected Discussion Rounds

1 раунд.

## Additional Context / Constraints (факты, принятые как вход)

1. **DeepSeek Harness (`dsh`)** — открытый харнесс агентного исполнения от DeepSeek AI (MIT), построен на парадигме Cordis «всё — плагин» (модель, инструменты, сессия, agent loop — заменяемые плагины). Профили: `web`, `headless` (одноразовый раннер без сервера), `sdk` (JSON-RPC сервер), `acp`; есть Python SDK, который упаковывает CLI `dsh --profile sdk` и запускает его как дочерний процесс. Есть subagent providers, workflow engine, append-only session log (JSONL с миграциями), sandbox/approval policy. СТАТУС: developer preview, README прямо предупреждает «THERE WILL BE COMPATIBILITY-BREAKING CHANGES»; SAFETY.md: ПО не проходила security audit, «must not be treated as secure or production-ready», рекомендует запуск в одноразовой VM/контейнере.
2. **«Текущая langchain-реализация» фактически не написана**: в репозитории ноль импортов langchain/langgraph. Stack Python+LangChain/LangGraph зафиксирован только в черновике `docs/en/project-reference/index.md` (статус draft). Кодовый Moderator не построен; сейчас Консилиум работает в fallback (субагенты OpenCode / Koda CLI профиль, документированный в `fallback/`).
3. **Реализовано и покрыто ~1000 тестов на Python**: `documenter_service/` (Tier 0–1 CLI + MCP stdio), `operator_surface/` (JSON-RPC stdio, pre_check gate, readiness sentinel), `tools/` (пишущий слой документа), translation CLI (внешний репо). Реестр аудита, canonical diff hash, одноразовые токены, dual interlock (policy + sentinel) — Python-реализации.
4. **Протокольные требования** (`docs/protocol-core`, `project-reference`): переходы между фазами вычисляются кодом из элементов артефактов (severity, stance, status, justification); критичная находка без валидного justification понижается механически; критичны канонический hash diff'а, approval binding, fail-closed реестр. Layer 0 planned-architecture запрещает ИМПОРТЫ любых фреймворков (в т.ч. LangChain/LangGraph) — ядро stack-neutral.
5. Проектный принцип: «что легко реализуется кодом — делается кодом; остальное — LLM». Fallback-профиль уже показал рабочий паттерн харнесса-оркестратора: роли = дочерние процессы с inline-контекстом, без инструментов, JSON envelope, acceptance-gate валидацией.
6. Оператор просит рассматривать варианты без связывания прежними ADR (ADR о стеке могут быть пересмотрены этим консенсусом).
