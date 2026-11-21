"""Source path resolution for Layer 2.

Provides ``resolve_doc(entry, repo_root)`` — safe path resolution that
rejects ``..`` traversal, absolute paths outside ``repo_root``, and
symlink components.

All source documents are:
  - English only (``docs/en/`` paths; ``docs/ru/`` excluded).
  - Non-archive (``status != "archive"``).
  - Existing on disk (readable file).
"""

import os


def resolve_doc(entry: dict, repo_root: str) -> str:
    """Разрешить путь документа из манифеста.

    Args:
        entry: Словарь документа из манифеста. Должен содержать ключи
               ``path`` и ``id``.
        repo_root: Абсолютный путь корня репозитория.

    Returns:
        Строка — абсолютный путь к файлу.

    Raises:
        ValueError: если путь содержит ``..`` traversal, абсолютный путь
                    вне ``repo_root``, или содержит symlink-компоненты.
        OSError: если файл не существует.
    """
    rel_path = entry.get("path", "")
    if not rel_path:
        raise ValueError(f"Document entry missing 'path': {entry.get('id', '<unknown>')}")

    # Проверка на .. traversal в компонентах пути
    parts = rel_path.split(os.sep)
    for part in parts:
        if part == "..":
            raise ValueError(
                f"Path traversal rejected: {rel_path!r} (entry {entry.get('id')!r})"
            )

    # Определяем абсолютный путь
    if os.path.isabs(rel_path):
        abs_path = rel_path
        # Абсолютные пути должны быть внутри repo_root
        try:
            relative = os.path.relpath(abs_path, repo_root)
        except ValueError:
            raise ValueError(
                f"Absolute path {abs_path!r} not under repo_root {repo_root!r}"
            )
        if relative.startswith(".."):
            raise ValueError(
                f"Absolute path {abs_path!r} is outside repo_root {repo_root!r}"
            )
    else:
        abs_path = os.path.join(repo_root, rel_path)

    # Проверка на symlink-компоненты (каждый компонент пути от repo_root до файла)
    rel_to_root = os.path.relpath(abs_path, repo_root)
    components = rel_to_root.split(os.sep)

    current = repo_root
    for comp in components:
        current = os.path.join(current, comp)
        if os.path.islink(current):
            raise ValueError(
                f"Symlink component rejected: {current!r} "
                f"(entry {entry.get('id')!r})"
            )

    # Проверка существования файла
    if not os.path.isfile(abs_path):
        raise OSError(f"Document file not found: {abs_path!r} (entry {entry.get('id')!r})")

    return abs_path


def is_en_doc(entry: dict) -> bool:
    """Проверить, является ли документ английским (не RU, не archive)."""
    status = entry.get("status", "")
    if status == "archive":
        return False
    path = entry.get("path", "")
    if "docs/ru/" in path or path.startswith("docs/ru/"):
        return False
    return True


def filter_valid_sources(
    entries: list[dict], repo_root: str
) -> list[dict]:
    """Фiltrровать и разрешить валидные источники.

    Возвращает список словарей с полями: id, path, abs_path, sha256,
    status, abstraction, section, kind.

    Пропускает:
      - RU-пути (docs/ru/).
      - status=archive.
      - Несуществующие файлы.
    """
    valid: list[dict] = []
    for entry in entries:
        if not is_en_doc(entry):
            continue

        abs_path = None
        try:
            abs_path = resolve_doc(entry, repo_root)
        except (ValueError, OSError):
            # Несуществующий файл или bad path — пропускаем
            continue

        # Вычисляем SHA-256
        import hashlib
        h = hashlib.sha256()
        with open(abs_path, "rb") as f:
            h.update(f.read())
        sha = h.hexdigest()

        # Определяем section по заголовку
        section = _extract_section(abs_path)

        valid.append({
            "id": entry.get("id", ""),
            "path": entry.get("path", ""),
            "abs_path": abs_path,
            "sha256": sha,
            "kind": "doc",
            "status": entry.get("status", "active"),
            "abstraction": entry.get("abstraction", ""),
            "section": section,
            "anchor": None,
            "lines": None,
            "symbol": None,
        })

    return valid


def _extract_section(abs_path: str) -> str:
    """Извлечь заголовок первого уровня (H1) из Markdown-файла."""
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
    except Exception:
        pass
    return "Introduction"
