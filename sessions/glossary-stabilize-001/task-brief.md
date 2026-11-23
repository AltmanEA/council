# Task Brief: Glossary Stabilization

### Session Goal
Оценить готовность документа `glossary` к переводу из статуса `draft` в `active` и принять консенсусное решение.

### Focus Areas
- Полнота определений: все термины корректно определены, без самопротиворечий
- Связность: все cross-references (`see also`) разрешены
- Структура: категории и логика разделения разделов осмыслены
- Статус `active` критерии: документ стабилен и не требует крупных переработок
- RU-версия: наличие и актуальность перевода

### Questionnaire per Role

**Architect:**
- Q1: Сохраняется ли логическая целостность структуры (категории, разделение терминов)?
- Q2: Есть ли unresolved cross-references или термины, на которые ссылаются другие документы, но которых нет в глоссарии?
- Q3: Нет ли дублирования определений или терминов, которые стоило бы перенести/переименовать?

**Reliability & Security Specialist:**
- Q1: Есть ли термины, связанные с безопасностью/надёжностью, которые недостаточно описаны или содержат неточности?
- Q2: Критичны ли статусы `Operational`/`Dormant` в глоссарии к текущему состоянию системы (ADR-013, ADR-014)?
- Q3: Нет ли risk-терминов (Escalation, Risk Threshold Breach), которые могут быть неверно истолкованы?

**Human-Centric Designer:**
- Q1: Являются ли определения достаточно понятными для конечного пользователя?
- Q2: Понятна ли структура категоризации? Легко ли найти нужный термин?
- Q3: Нет ли перегруженности (слишком много терминов в одном разделе) или, наоборот, пустых/неясных категорий?

### Output Limits
- Maximum findings per role: 5
- Maximum recommendations per role: 3
- Maximum open questions per role: 2
- Total output: ~150 lines

### Expected Discussion Rounds
- **0 rounds** for initial review — this is a focused assessment, not a complex design review

### Subject List
- [SUBJ-001]: Glossary document status transition from draft to active
- [SUBJ-002]: Glossary structural integrity and cross-reference resolution
- [SUBJ-003]: Glossary term completeness and accuracy relative to current project state

### Additional Context / Constraints
- Текущая версия: 0.16.0 (draft)
- RU-версия существует по пути: docs/ru/glossary/index-RU.md
- В манифесте только `protocol-core` имеет статус `active` (v0.6.0)
- Глоссарий ссылается на protocol-core, documenter-service, planned-architecture, scenario, service-contract, translation-project
- Все термины в глоссарии должны быть использованы в других документах (проверить обратные ссылки)
- Задача: оценить, готов ли глоссарий к `active`, или есть блокирующие проблемы
