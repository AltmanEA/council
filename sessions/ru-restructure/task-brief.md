# Task Brief — RU Files Restructure

## Session Goal

Определить, стоит ли перенести все файлы с русскими переводами из `docs/<folder>/index-RU.md` в отдельный каталог (например, `docs/ru/`) и какие последствия это повлечёт для манифеста, ссылок и рабочих процессов.

## Focus Areas

- Архитектурные последствия: как изменится навигация для ИИ и для человека
- Манифест: нужно ли менять `has_translation: index-RU.md` на новый формат
- Трансформация: какой будет путь к перенесённым файлам
- Риски: что ломается при переносе

## Questionnaire per Role

**Architect:**
- Q1: Разделение по папкам — снижает или увеличивает когнитивную нагрузку для ИИ при чтении оригиналов?
- Q2: Какой путь к переводам будет интуитивно понятен человеку (docs/ru/… или ru/…)?
- Q3: Как изменится структура манифеста и какие поля понадобятся для указания пути к RU?

**Reliability & Security Specialist:**
- Q1: Не потеряются ли переводы при рефакторинге дерева каталогов?
- Q2: Как избежать рассинхронизации оригинал-перевод при раздельном хранении?
- Q3: Какие риски для манифеста (ссылки, path references)?

**Human-Centric Designer:**
- Q1: Будет ли человеку проще искать переводы в отдельной папке?
- Q2: Как это скажется на привычном процессе чтения на русском?
- Q3: Не создаст ли путаницы с дублированием структуры каталогов?

## Output Limits
- Maximum findings per role: 5
- Maximum recommendations per role: 3
- Maximum open questions per role: 2
- Total output: ~150 lines

## Expected Discussion Rounds
- Simple task: 0 rounds → jump from review directly to consensus check

## Subject List
- [SUBJ-001]: Перенос 14 файлов `*RU.md` из текущих `docs/<folder>/` в отдельный каталог
- [SUBJ-002]: Обновление `docs-manifest.yaml` — изменение формата `has_translation` на абсолютный путь
- [SUBJ-003]: Влияние на рабочий процесс (translation workflow per AGENTS.md §3.3)

## Additional Context / Constraints

- В манифесте 14 записей с `has_translation` — все ссылаются на `index-RU.md` или аналогичные имена файлов в той же папке
- `planned-architecture/` содержит `layer-0-RU.md`, `layer-1-RU.md`, `layer-2-RU.md`, `decisions/index-RU.md`
- `service-contract/` содержит `error-management-RU.md`
- Переводы предназначены для чтения человеком, оригиналы — для чтения ИИ
- По AGENTS.md §3.3 переводы являются secondary/derivative — English is the source of truth
- Фраза "обоим будет проще, если у каждого будет своя папка с документацией" — основная мотивация
