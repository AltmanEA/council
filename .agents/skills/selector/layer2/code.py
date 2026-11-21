"""Code body scanning for Layer 2 (opt-in via ``reveal_code``).

When ``reveal_code=True``, this module:
  - Scans .py files from the manifest for injection patterns.
  - Searches for files matching ``query`` in the repo.
  - Excludes paths listed in ``excluded_paths``.

When ``reveal_code=False``, code.search is NOT called and .py files
are excluded from ``sources`` (but still scanned for injections if
they appear in the manifest).
"""

import os
import re


# Паттерны инъекций — совпадают с INJECTION_PATTERNS из Layer 1
_INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(previous\s+)?instructions",
    r"(?i)you\s+are\s+now",
    r"(?i)bypass\s+security",
    r"(?i)disregard\s+all\s+previous",
    r"(?i)from\s+now\s+on",
    r"(?i)you\s+must\s+(now|ignore)",
]


def search(
    repo_root: str,
    query: str,
    excluded_paths: list[str] | None = None,
) -> list[str]:
    """Найти Python-файлы в ``repo_root``, релевантные запросу.

    Args:
        repo_root: Корень репозитория.
        query: Текстовый запрос (ищется по имени файла и первому слову пути).
        excluded_paths: Список путей, которые нужно исключить.

    Returns:
        Отсортированный список абсолютных путей к .py-файлам.
    """
    if excluded_paths is None:
        excluded_paths = []

    abs_excluded = set(os.path.abspath(p) for p in excluded_paths)

    matches: list[str] = []
    query_lower = query.lower()

    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Skip hidden directories
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for fname in filenames:
            if not fname.endswith(".py"):
                continue

            abs_path = os.path.join(dirpath, fname)

            # Проверка excluded
            if abs_path in abs_excluded:
                continue
            # Проверка, что путь не выходит за repo_root
            try:
                rel = os.path.relpath(abs_path, repo_root)
            except ValueError:
                continue
            if rel.startswith(".."):
                continue

            # Простая проверка релевантности по имени/пути
            path_lower = abs_path.lower()
            if query_lower in path_lower or query_lower in fname.lower():
                matches.append(abs_path)

    matches.sort()
    return matches


def scan_for_injections(abs_path: str) -> tuple[bool, int]:
    """Сканировать файл на инъекции.

    Args:
        abs_path: Абсолютный путь к файлу.

    Returns:
        (detected, count) — обнаружены ли инъекции и их количество.
    """
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return False, 0

    count = 0
    for pat in _INJECTION_PATTERNS:
        count += len(re.findall(pat, text))

    return count > 0, count
