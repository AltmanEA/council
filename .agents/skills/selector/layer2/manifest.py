"""Manifest loading and discovery helpers for Layer 2.

Uses Layer 1 runtime ``load_manifest`` and ``discover`` where available;
falls back to a simple YAML-like parser for the subset of fixtures in use.
"""

import hashlib
import os
import re

# ---------------------------------------------------------------------------
# Инъекционные шаблоны (совпадают с Layer 1 INJECTION_PATTERNS)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(previous\s+)?instructions",
    r"(?i)you\s+are\s+now",
    r"(?i)bypass\s+security",
    r"(?i)disregard\s+all\s+previous",
    r"(?i)from\s+now\s+on",
    r"(?i)you\s+must\s+(now|ignore)",
]


def _sha256_of(path: str) -> str:
    """Вычислить SHA-256 файла."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _count_injections(text: str) -> tuple[bool, int]:
    """Вернуть (detected, count) совпадений инъекционных паттернов."""
    count = 0
    for pat in _INJECTION_PATTERNS:
        count += len(re.findall(pat, text))
    return count > 0, count


def load_manifest(path: str) -> tuple[list[dict], str, bool, int, str]:
    """Загрузить и проверить манифест (fail-closed).

    Args:
        path: Путь к YAML-файлу манифеста.

    Returns:
        (entries, manifest_sha256, injection_detected, injection_count, error_text)
    """
    manifest_sha = ""
    raw_injected = False
    raw_count = 0

    try:
        manifest_sha = _sha256_of(path)

        # Проверим сырой текст на инъекции
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        detected, cnt = _count_injections(raw_text)
        if detected:
            raw_injected = True
            raw_count = cnt

        # Попробуем импортировать Layer 1 runtime
        try:
            import importlib
            _runtime = importlib.import_module(
                "selector_runtime",
                __import__("sys").modules.get("selector_runtime"),
            )
            entries, m_sha, inj_det, inj_cnt, err = _runtime.discover(path)
            if err:
                return [], manifest_sha, raw_injected, raw_count, err
            return entries, manifest_sha, raw_injected or inj_det, raw_count + inj_cnt, ""
        except (ImportError, AttributeError):
            pass

        # Fallback-парсер
        entries = _parse_manifest_text(raw_text)
        if not entries:
            return [], manifest_sha, raw_injected, raw_count, "Manifest is empty — no documents found"
        return entries, manifest_sha, raw_injected, raw_count, ""

    except FileNotFoundError:
        return [], manifest_sha, False, 0, f"Manifest file not found: {path}"
    except Exception as exc:
        return [], manifest_sha, raw_injected, raw_count, f"Manifest parse error: {exc}"


def _parse_manifest_text(text: str) -> list[dict]:
    """Простой fallback-парсер для YAML-фикстур (documents: [...] формат)."""
    if "documents:" not in text:
        return []

    entries: list[dict] = []
    current: dict[str, str] = {}
    in_docs = False

    for line in text.split("\n"):
        if line.strip() == "documents:":
            in_docs = True
            continue
        if not in_docs:
            continue

        stripped = line.strip()

        # Новый документ
        m = re.match(r"^-\s+id:\s*(.+)$", stripped)
        if m:
            if current:
                entries.append(current)
            current = {"id": m.group(1).strip()}
            continue

        # Поле ключ: значение
        if stripped and current and ": " in stripped:
            key, value = stripped.split(": ", 1)
            current[key.strip()] = value.strip().strip('"').strip("'")

    if current:
        entries.append(current)

    return entries


def discover_repo_root(manifest_path: str) -> str:
    """Определить корень репозитория, поднявшись вверх от манифеста.

    Ищет каталог с .git или docs-manifest.yaml; при неудаче — возвращает
    родительскую директорию манифеста.
    """
    candidate = os.path.abspath(manifest_path)
    # Поднимаемся до каталога
    if os.path.isfile(candidate):
        candidate = os.path.dirname(candidate)

    while candidate and candidate != "/":
        if os.path.isfile(os.path.join(candidate, ".git")) or \
           os.path.isfile(os.path.join(candidate, ".git", "HEAD")):
            return candidate
        if os.path.isfile(os.path.join(candidate, "docs-manifest.yaml")):
            return candidate
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent

    # Fallback — родитель манифеста
    return os.path.dirname(os.path.abspath(manifest_path))
