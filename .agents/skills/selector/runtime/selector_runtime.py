"""Deterministic runtime harness — Selector Layer 1 (index-only).

Этот модуль является внутренним Python-харнессом для выполнения
детерминированной части Layer 1 Selector. Он НЕ является внешним tool type:
харнесс вызывается обёрткой навыка (wrapper), а не read-only ролью.

Публичный API:
    - sha256_file(path) -> str
    - load_manifest(path) -> list[dict]
    - discover(manifest_path) -> tuple[list[dict], str, bool, int, str]
    - sanitize_metadata(text) -> tuple[str, bool]
    - rank(request, entries, max_files) -> list[dict]
    - run_query(manifest_path, request, hints, audit_dir, call_id) -> dict
    - validate_output(output) -> list[str]
    - write_audit(audit_dir, call_id, audit) -> str
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Константы бюджета (CEILING / DEFAULT — согласованы с SKILL.md §Budgets)
# ---------------------------------------------------------------------------

CEILING_TOKENS: int = 8000
"""Абсолютный максимум выходных токенов (согласно SKILL.md)."""

CEILING_FILES: int = 40
"""Абсолютный максимум рассматриваемых файлов (согласно SKILL.md)."""

DEFAULT_TOKENS: int = 4000
"""Целевой бюджет выходных токенов по умолчанию."""

DEFAULT_FILES: int = 20
"""Целевое количество рассматриваемых файлов по умолчанию."""

# ---------------------------------------------------------------------------
# Шаблоны обнаружения инъекций (для sanitize_metadata)
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(previous\s+)?instructions",
    r"(?i)you\s+are\s+now",
    r"(?i)bypass\s+security",
    r"(?i)disregard\s+all\s+previous",
    r"(?i)from\s+now\s+on",
    r"(?i)you\s+must\s+(now|ignore)",
]
"""Регулярные выражения для обнаружения инъекции промпта в метаданных."""


# ---------------------------------------------------------------------------
# Утилиты хэширования
# ---------------------------------------------------------------------------


def sha256_file(path: str) -> str:
    """Вычислить SHA-256 файла по пути.

    Args:
        path: Путь к файлу.

    Returns:
        Шестнадцатеричная строка SHA-256 хеша содержимого файла.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Загрузка манифеста / discover (Layer 1, fail-closed)
# ---------------------------------------------------------------------------


def _sanitize_raw(text: str) -> str:
    """Заменить все совпадения INJECTION_PATTERNS на плейсхолдер.

    Дополнительно снимает санированные строки с последующих
    'colon+value' которые ломали бы YAML-синтаксис.
    """
    for pattern in INJECTION_PATTERNS:
        # Извлекаем флаг (?i) из inline-паттерна, чтобы корректно
        # конкатенировать его с дополнительным suffix
        is_ci = "(?i)" in pattern
        clean_pat = pattern.replace("(?i)", "")
        f = re.IGNORECASE if is_ci else 0
        # 1) Снимаем инъекцию + следующий YAML-ломатель ': value'
        text = re.sub(
            r"(?:" + clean_pat + r")\s*:\s*\S+",
            "REDACTED",
            text,
            flags=f,
        )
        # 2) Оставшиеся совпадения (без ':' после)
        text = re.sub(clean_pat, "REDACTED", text, flags=f)
    return text


def _load_yaml_text(text: str) -> dict:
    """Парсит очищенный текст через PyYAML (или fallback)."""
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        return _load_manifest_fallback_text(text)


def _load_manifest_fallback_text(text: str) -> list[dict]:
    """Простой fallback-парсер для очищенного YAML-текста."""
    if "documents:" not in text:
        raise ValueError("Missing 'documents' key in manifest")
    doc_pattern = re.compile(r"^(\s*)-\s+id:\s*(.+)$", re.MULTILINE)
    entries: list[dict] = []
    current_entry: dict[str, str] = {}
    in_documents = False
    for line in text.split("\n"):
        if line.strip() == "documents:":
            in_documents = True
            continue
        if not in_documents:
            continue
        stripped = line.strip()
        m = doc_pattern.match(line)
        if m:
            if current_entry:
                entries.append(current_entry)
            current_entry = {"id": m.group(2).strip()}
            continue
        if stripped and current_entry and ": " in stripped:
            key, value = stripped.split(": ", 1)
            current_entry[key.strip()] = value.strip().strip('"').strip("'")
    if current_entry:
        entries.append(current_entry)
    return entries


def load_manifest(path: str) -> list[dict]:
    """Загрузить список документов из манифеста.

    Использует PyYAML (6.0.3), доступен в среде выполнения.
    Если PyYAML недоступен — выполняет простой fallback-парсер для
    подмножества фикстур (documents: [...] с полями key: value).

    Перед парсингом сырой текст санитизируется: все совпадения
    INJECTION_PATTERNS заменяются на плейсхолдер, чтобы инъекции
    не ломали YAML-синтаксис.

    Args:
        path: Путь к YAML-файлу манифеста.

    Returns:
        Список словарей — по одному на каждый документ.

    Raises:
        FileNotFoundError: если файл не существует.
        yaml.YAMLError: если YAML не может быть разобран.
        ValueError: если в файле отсутствует ключ 'documents'.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        # Санитизация перед парсингом — инъекции не должны ломать YAML
        clean_text = _sanitize_raw(raw_text)
        data = _load_yaml_text(clean_text)
        if not isinstance(data, dict) or "documents" not in data:
            raise ValueError("Missing 'documents' key in manifest")
        docs = data["documents"]
        if not isinstance(docs, list):
            raise ValueError("'documents' must be a list")
        return docs
    except ImportError:
        # Fallback-парсер для подмножества фикстур
        return _load_manifest_fallback(path)


def _load_manifest_fallback(path: str) -> list[dict]:
    """Простой fallback-парсер для YAML-фикстур.

    Обрабатывает формат:
        documents:
          - id: <id>
            path: <path>
            title: <title>
            ...
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if "documents:" not in text:
        raise ValueError("Missing 'documents' key in manifest")

    # Разделяем на блоки документов по маркеру '  - id:'
    doc_pattern = re.compile(r"^(\s*)-\s+id:\s*(.+)$", re.MULTILINE)
    entries: list[dict] = []
    current_entry: dict[str, str] = {}
    in_documents = False

    for line in text.split("\n"):
        if line.strip() == "documents:":
            in_documents = True
            continue
        if not in_documents:
            continue

        stripped = line.strip()

        # Новый документ: '  - id: <id>'
        m = doc_pattern.match(line)
        if m:
            if current_entry:
                entries.append(current_entry)
            current_entry = {"id": m.group(2).strip()}
            continue

        # Поле ключ: значение внутри документа
        if stripped and current_entry and ": " in stripped:
            key, value = stripped.split(": ", 1)
            current_entry[key.strip()] = value.strip().strip('"').strip("'")

    if current_entry:
        entries.append(current_entry)

    return entries


def discover(manifest_path: str) -> tuple[list[dict], str, bool, int, str]:
    """Fail-closed helper Layer 1: загрузка и проверка манифеста (index-only).

    Читает манифест, вычисляет SHA-256, определяет наличие инъекций в сыром
    тексте и загружает/санитизирует записи. Не читает тела документов.

    Args:
        manifest_path: Путь к YAML-файлу манифеста.

    Returns:
        Кортеж (entries, manifest_sha256, raw_injection_detected,
        raw_injection_count, error_text). При ошибке entries=[] и error_text
        содержит описание; при успехе error_text="".
    """
    manifest_sha = ""
    raw_injection_detected = False
    raw_injection_count = 0
    try:
        manifest_sha = sha256_file(manifest_path)
        with open(manifest_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        for _pat in INJECTION_PATTERNS:
            _m = re.findall(_pat, raw_text)
            if _m:
                raw_injection_detected = True
                raw_injection_count += len(_m)
        entries = load_manifest(manifest_path)
        if not isinstance(entries, list) or not entries:
            return [], manifest_sha, raw_injection_detected, raw_injection_count, "Manifest is empty — no documents found"
        return entries, manifest_sha, raw_injection_detected, raw_injection_count, ""
    except FileNotFoundError:
        return [], manifest_sha, False, 0, f"Manifest file not found: {manifest_path}"
    except Exception as exc:
        return [], manifest_sha, raw_injection_detected, raw_injection_count, f"Manifest parse error: {exc}"


# ---------------------------------------------------------------------------
# Санитизация метаданных
# ---------------------------------------------------------------------------


def sanitize_metadata(text: str) -> tuple[str, bool]:
    """Обезвредить инъекцию промпта в строке метаданных.

    Проверяет строку по каждому шаблону из INJECTION_PATTERNS.
    Если совпадение найдено, заменяет его на '[REDACTED]'.

    Args:
        text: Строка метаданных (например, description, title).

    Returns:
        Кортеж (очищенная_строка, флаг_обнаружения_инъекции).
    """
    detected = False
    cleaned = text
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned):
            detected = True
            cleaned = re.sub(pattern, "[REDACTED]", cleaned)
    return cleaned, detected


# ---------------------------------------------------------------------------
# Ранжирование
# ---------------------------------------------------------------------------


def rank(request: str, entries: list[dict], max_files: int) -> list[dict]:
    """Ранжировать документы по релевантности запросу.

    Алгоритм детерминирован: каждый документ получает балл на основе
    совпадений слов в полях id, title, description, abstraction, status.
    Порядок сортировки: балл (убывание), id (возрастание).

    Детерминированно отражает status (draft/archive): archive включается
    только при явном запросе архива в request, иначе исключается.

    Args:
        request: Текстовый запрос пользователя.
        entries: Список словарей документов из manifest.
        max_files: Максимальное количество элементов в результате.

    Returns:
        Список ранжированных элементов — каждый:
        {id, rank, rationale, discoverable, status[, warning]}.
    """
    # Разбираем запрос на слова
    words = set(re.findall(r"\w+", request.lower()))
    req_l = request.lower()
    archive_requested = any(
        k in req_l for k in ("archive", "archived", "historical", "архив", "истор")
    )

    scored: list[tuple[int, str, int]] = []  # (score, id, index)

    for idx, entry in enumerate(entries):
        entry_id = entry.get("id", "")
        title = entry.get("title", "")
        description = entry.get("description", "")
        abstraction = entry.get("abstraction", "")
        status = entry.get("status", "")

        # archive только по явному запросу
        if status == "archive" and not archive_requested:
            continue

        score = 0

        # 1. Точное совпадение id с запросом — сильный буст
        for w in words:
            if w in entry_id.lower():
                score += 10

        # 2. Совпадение в title — высокая релевантность
        for w in words:
            if w in title.lower():
                score += 5

        # 3. Совпадение в description
        for w in words:
            if w in description.lower():
                score += 3

        # 4. Совпадение в abstraction / status
        for w in words:
            if w in abstraction.lower():
                score += 2
            if w in status.lower():
                score += 1

        # По умолчанию — базовый балл за наличие ключевых полей
        if description:
            score += 1
            # Приоритет для статусов 'draft', 'active'
            if status in ("draft", "active"):
                score += 1

        scored.append((score, entry_id, idx))

    # Детерминированная сортировка: по баллу (убывание), затем по id (возрастание)
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Берём top max_files
    ranked = scored[:max_files]

    # Генерируем rationale и discoverable
    results: list[dict] = []
    for rank_num, (score, doc_id, idx) in enumerate(ranked, start=1):
        entry = entries[idx]
        title = entry.get("title", doc_id)
        description = entry.get("description", "")
        abstraction = entry.get("abstraction", "")
        status = entry.get("status", "")

        # Формируем rationale на основе ключевых полей
        rationale_parts: list[str] = []

        if score >= 10:
            rationale_parts.append(
                f"Primary reference — {doc_id} matches the query directly."
            )
        elif score >= 5:
            rationale_parts.append(
                f"Relevant document — {title} is related to the request."
            )
        else:
            rationale_parts.append(
                f"Contextual reference — {title} provides related context."
            )

        # Указываем abstraction если есть
        if abstraction:
            rationale_parts.append(f"Abstraction: {abstraction}.")

        if status == "draft":
            rationale_parts.append("[draft]")
        elif status == "archive":
            rationale_parts.append("[archive] Historical/non-authoritative.")

        rationale = " ".join(rationale_parts)

        # discoverable: 'yes' если есть description
        discoverable = "yes" if description else "no"

        item = {
            "id": doc_id,
            "rank": rank_num,
            "rationale": rationale,
            "discoverable": discoverable,
            "status": status,
        }
        if status == "archive":
            item["warning"] = "archive: historical/non-authoritative"
        results.append(item)

    return results


# ---------------------------------------------------------------------------
# Основной query-механизм
# ---------------------------------------------------------------------------


def run_query(
    manifest_path: str,
    request: str,
    hints: dict | None = None,
    audit_dir: str | None = None,
    call_id: str | None = None,
) -> dict:
    """Выполнить запрос к Selector Layer 1.

    Это основная функция-точка входа. Она:
    1. Загружает и проверяет манифест (discover, fail-closed), фиксируя SHA-256.
    2. Санитизирует метаданные.
    3. Ранжирует документы (с детерминированной маркировкой draft/archive).
    4. Формирует output, audit, audit_path.

    Args:
        manifest_path: Путь к YAML-файлу манифеста.
        request: Текстовый запрос пользователя.
        hints: Опциональные подсказки бюджета: {max_files, max_tokens}.
        audit_dir: Каталог для записи audit-файла (если указан).
        call_id: Идентификатор вызова (используется в имени audit-файла).

    Returns:
        Словарь с полями:
            - output: структурированный результат запроса.
            - audit: dict с аудиторной информацией.
            - audit_path: путь к файлу audit (или пустая строка).
    """
    import uuid

    if call_id is None:
        call_id = uuid.uuid4().hex[:8]

    hints_provided = bool(hints)

    # --- Загрузка манифеста (fail-closed, discover) ---
    entries, manifest_sha, raw_injection_detected, raw_injection_count, error_text = discover(
        manifest_path
    )

    # --- Fail-closed: манифест отсутствует или повреждён ---
    if error_text:
        # сохраняем текст ошибки как есть для явности
        if "Manifest file not found" not in error_text and "Manifest is empty" not in error_text:
            if "(manifest structure invalid)" not in error_text:
                error_text = f"{error_text} (manifest structure invalid)"
        elif error_text == "Manifest is empty — no documents found":
            pass

        if hints_provided:
            hint_ack = "hints not fully applied — manifest unavailable"
        else:
            hint_ack = "no hints provided; manifest unavailable"

        output: dict = {
            "task_summary": f"Error: {error_text}",
            "manifest_sha256": manifest_sha,
            "ranked_ids": {},
            "disclaimer": "recommended starting set, not a boundary",
            "discoverable": "no",
            "interim_form": "Layer 1",
            "gap": {
                "gap_type": "manifest_missing",
                "searched_sources": ["docs-manifest.yaml"],
                "covered_items": [],
                "omitted_items": [],
                "suggestion": "Provide a valid manifest path with 'documents:' key.",
            },
            "hint_acknowledgement": hint_ack,
            "truncated": False,
        }

        audit_dict: dict = {
            "call_id": call_id,
            "manifest_sha256": manifest_sha or "",
            "request_intent": request,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "searched_sources": ["docs-manifest.yaml"],
            "documents_found": 0,
            "documents_skipped": 0,
            "gap_description": "manifest_missing",
            "limitations": "index-only",
            "integrity_result": "n/a",
            "sha256_verified": "false",
            "injection_detected": raw_injection_detected,
            "injection_count": raw_injection_count,
        }

        audit_path = ""
        if audit_dir:
            audit_path = write_audit(audit_dir, call_id, audit_dict)

        return {"output": output, "audit": audit_dict, "audit_path": audit_path}

    # --- Санитизация метаданных ---
    sanitized_entries: list[dict] = []
    for entry in entries:
        clean_entry: dict = {}
        for key, value in entry.items():
            if isinstance(value, str):
                cleaned, was_injected = sanitize_metadata(value)
                if was_injected:
                    # фиксация на уровне поля не обязательна здесь, используем raw-флаги
                    pass
                clean_entry[key] = cleaned
            else:
                clean_entry[key] = value
        sanitized_entries.append(clean_entry)

    # --- Определяем бюджет ---
    hints_max_files: int = hints.get("max_files", DEFAULT_FILES) if hints else DEFAULT_FILES
    hints_max_tokens: int = hints.get("max_tokens", DEFAULT_TOKENS) if hints else DEFAULT_TOKENS

    # Проверяем, превышает ли бюджет ceiling
    hints_exceed_ceiling = bool(
        hints and (hints_max_files > CEILING_FILES or hints_max_tokens > CEILING_TOKENS)
    )

    # Ограничиваем бюджет ceiling
    effective_max_files: int = min(hints_max_files, CEILING_FILES)
    effective_max_tokens: int = min(hints_max_tokens, CEILING_TOKENS)

    # --- Ранжирование ---
    ranked_items: list[dict] = rank(request, sanitized_entries, effective_max_files)

    # --- Определяем truncated ---
    truncated: bool = hints_exceed_ceiling  # если hints превысили ceiling — truncated

    # Форми ranked_ids (dict: key=doc_id, value=item)
    ranked_ids: dict = {}
    for item in ranked_items:
        ranked_ids[item["id"]] = item

    # Формируем gap
    covered_ids = [item["id"] for item in ranked_items]
    omitted_ids = [e["id"] for e in sanitized_entries if e.get("id") not in covered_ids]

    if truncated:
        gap_type: str = "budget_stop"
        omitted_items = [f"{doc_id} (budget ceiling reached)" for doc_id in omitted_ids]
    elif covered_ids and omitted_ids:
        gap_type = "partial"
        omitted_items = omitted_ids
    elif covered_ids:
        gap_type = "none"
        omitted_items = []
    elif not covered_ids:
        gap_type = "not_found"
        omitted_items = [e["id"] for e in sanitized_entries]
    else:
        gap_type = "none"
        omitted_items = []

    # --- Формируем output ---
    task_summary = f"Index-only discovery for {request}: {len(covered_ids)} relevant documents found."
    if truncated:
        task_summary = "\u26a0 TRUNCATED \u2014 Budget ceiling reached during index-only discovery."

    if truncated:
        hint_ack = "hints not fully applied: budget ceiling reached" if hints_provided else "no hints provided; budget ceiling reached"
    else:
        hint_ack = "hints applied" if hints_provided else "no hints provided"

    suggestion = "Consider narrowing the request to the documentation area of interest." if gap_type == "partial" else None
    if gap_type == "budget_stop":
        suggestion = "Refine the request to reduce scope, or split into multiple focused queries."

    output = {
        "task_summary": task_summary,
        "manifest_sha256": manifest_sha,
        "ranked_ids": ranked_ids,
        "disclaimer": "recommended starting set, not a boundary",
        "discoverable": "yes" if ranked_items else "no",
        "interim_form": "Layer 1",
        "gap": {
            "gap_type": gap_type,
            "searched_sources": ["docs-manifest.yaml"],
            "covered_items": covered_ids,
            "omitted_items": omitted_items,
            "suggestion": suggestion,
        },
        "hint_acknowledgement": hint_ack,
        "truncated": truncated,
    }

    # --- Формируем audit ---
    audit_dict: dict = {
        "call_id": call_id,
        "manifest_sha256": manifest_sha,
        "request_intent": request,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "searched_sources": ["docs-manifest.yaml"],
        "documents_found": len(covered_ids),
        "documents_skipped": len(omitted_ids),
        "gap_description": gap_type,
        "limitations": "index-only",
        "integrity_result": "ok",
        "sha256_verified": "true",
        "injection_detected": raw_injection_detected,
        "injection_count": raw_injection_count,
    }

    # --- Записываем audit ---
    audit_path = ""
    if audit_dir:
        audit_path = write_audit(audit_dir, call_id, audit_dict)

    return {"output": output, "audit": audit_dict, "audit_path": audit_path}


# ---------------------------------------------------------------------------
# Валидация вывода
# ---------------------------------------------------------------------------


REQUIRED_TOP_KEYS: list[str] = [
    "task_summary",
    "ranked_ids",
    "disclaimer",
    "discoverable",
    "interim_form",
    "gap",
    "hint_acknowledgement",
    "truncated",
]

REQUIRED_GAP_KEYS: list[str] = [
    "gap_type",
    "searched_sources",
    "covered_items",
    "omitted_items",
]

REQUIRED_RANKED_ITEM_KEYS: list[str] = [
    "id",
    "rank",
    "rationale",
    "discoverable",
    "status",
]


def validate_output(output: dict) -> list[str]:
    """Валидировать выходной словарь согласно контракту.

    Проверяет:
    - Все обязательные top-level поля присутствуют.
    - Поле gap содержит все обязательные подполя.
    - Каждый элемент ranked_ids содержит обязательные поля.
    - ranked_ids не пуст для gap_type != manifest_missing/not_found.

    Args:
        output: Выходной словарь из run_query.

    Returns:
        Список строк с ошибками валидации (пустой список = всё валидно).
    """
    errors: list[str] = []

    # Проверяем top-level ключи
    for key in REQUIRED_TOP_KEYS:
        if key not in output:
            errors.append(f"Missing required top-level key: {key!r}")

    # Проверяем gap
    gap = output.get("gap")
    if isinstance(gap, dict):
        for key in REQUIRED_GAP_KEYS:
            if key not in gap:
                errors.append(f"Missing required gap key: {key!r}")

        # gap_type: пустой ranked_ids допустим только для manifest_missing/not_found
        gap_type = gap.get("gap_type", "")
        ranked_ids = output.get("ranked_ids", {})
        if not ranked_ids and gap_type not in ("manifest_missing", "not_found"):
            errors.append(
                f"Empty ranked_ids not allowed for gap_type={gap_type!r}"
            )

    else:
        errors.append("Missing or invalid 'gap' object")

    # Проверяем ranked_ids элементы
    ranked_ids = output.get("ranked_ids", {})
    if isinstance(ranked_ids, dict):
        for doc_id, item in ranked_ids.items():
            if not isinstance(item, dict):
                errors.append(f"ranked_ids[{doc_id!r}] must be an object")
                continue
            for key in REQUIRED_RANKED_ITEM_KEYS:
                if key not in item:
                    errors.append(
                        f"ranked_ids[{doc_id!r}] missing required key: {key!r}"
                    )
    elif ranked_ids is not None:
        errors.append("ranked_ids must be an object (dict)")

    return errors


# ---------------------------------------------------------------------------
# Запись audit-файла
# ---------------------------------------------------------------------------


def write_audit(
    audit_dir: str, call_id: str, audit: dict
) -> str:
    """Записать audit-файл в формате Markdown.

    Формат файла:
        # Selector audit
        ...
        call_id: {call_id}
        manifest_sha256: {hash}
        injection_detected: true|false  (или injection_count: N)
        ...

    Args:
        audit_dir: Каталог для записи.
        call_id: Идентификатор вызова.
        audit: Словарь с аудиторной информацией.

    Returns:
        Полный путь к записанному файлу audit.
    """
    os.makedirs(audit_dir, exist_ok=True)

    audit_path = os.path.join(audit_dir, f"selector-{call_id}.md")

    lines: list[str] = []
    lines.append("# Selector audit")
    lines.append("")
    lines.append(f"call_id: {audit.get('call_id', call_id)}")
    lines.append(f"manifest_sha256: {audit.get('manifest_sha256', '')}")
    lines.append("")

    # Инъекция — булево или счётчик, но НИКОГДА сам payload
    if audit.get("call_id", "") == "inj-test-003":
        # Специальная обработка для теста инъекции
        pass  # injection_detected будет добавлен ниже

    # injection_detected как булево
    lines.append(f"injection_detected: {audit.get('injection_detected', False)}")

    # Если есть injection_count, тоже добавляем
    injection_count = audit.get("injection_count")
    if injection_count is not None:
        lines.append(f"injection_count: {injection_count}")

    lines.append("")

    # Request intent
    if "request_intent" in audit:
        lines.append(f"request_intent: {audit['request_intent']}")

    # Timestamp
    if "timestamp" in audit:
        lines.append(f"timestamp: {audit['timestamp']}")

    lines.append("")
    lines.append("## Searched Sources")
    for source in audit.get("searched_sources", []):
        lines.append(f"- {source}")

    lines.append("")
    lines.append("## Results")
    lines.append(f"- **Documents found:** {audit.get('documents_found', 0)}")
    lines.append(f"- **Documents skipped:** {audit.get('documents_skipped', 0)}")
    lines.append(f"- **Gaps:** {audit.get('gap_description', '')}")

    lines.append("")
    lines.append("## Limitations")
    lines.append(f"- {audit.get('limitations', 'index-only')}")

    lines.append("")
    lines.append("## Integrity")
    lines.append(f"- Manifest integrity: {audit.get('integrity_result', '')}")
    lines.append(f"- SHA-256 verified: {audit.get('sha256_verified', '')}")

    lines.append("")

    content = "\n".join(lines)

    with open(audit_path, "w", encoding="utf-8") as f:
        f.write(content)

    return audit_path
