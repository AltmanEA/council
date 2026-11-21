"""Evidence fact generation for Layer 2.

Builds ``facts[]`` entries from document content:
  - Extracts the first sentence from the EN document body.
  - Falls back to the manifest ``description`` field.
  - Attaches the source document IDs.

Each fact has ``claim``, ``sources[]`` (document IDs), and ``status``.
"""

import re

try:
    from . import sanitize as _sanitize_mod
except ImportError:
    import importlib
    _sanitize_mod = importlib.import_module("selector_layer2.sanitize")


def build_facts(
    sources: list[dict],
    ranked_entries: list[dict],
) -> list[dict]:
    """Сгенерировать facts[] из источников и ранжированных документов.

    Args:
        sources: Список разрешённых источников (из ``sources.filter_valid_sources``).
        ranked_entries: Ранжированные документы (с id, title, description, status).

    Returns:
        Список fact-словарей: {claim, sources[], status}.
    """
    facts: list[dict] = []

    for src in sources:
        doc_id = src["id"]
        claim = _extract_claim(src, ranked_entries)

        if claim:
            facts.append({
                "claim": claim,
                "sources": [doc_id],
                "status": "verified",
            })

    return facts


def _extract_claim(src: dict, ranked_entries: list[dict]) -> str | None:
    """Извлечь claim из источника.

    Приоритет:
      1. Первое предложение из тела документа.
      2. description из ранжированного entry.
      3. None (пропустить факт).

    Результат санитизируется через sanitize.scrub().
    """
    # 1. Попробуем первое предложение из документа
    first_sentence = _first_sentence_from_path(src.get("abs_path", ""))
    if first_sentence:
        cleaned, _ = _sanitize_mod.scrub(first_sentence)
        return cleaned

    # 2. Попробуем description из entry
    for entry in ranked_entries:
        if entry.get("id") == src["id"]:
            desc = entry.get("description", "")
            if desc:
                cleaned, _ = _sanitize_mod.scrub(desc)
                cleaned = _truncate_to_sentence(cleaned)
                return cleaned

    return None


def _first_sentence_from_path(abs_path: str) -> str | None:
    """Извлечь первое предложение из Markdown-файла."""
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Пропускаем заголовки
                if line.startswith("#"):
                    continue
                if line:
                    return _truncate_to_sentence(line)
    except Exception:
        pass
    return None


def _truncate_to_sentence(text: str) -> str | None:
    """Обрезать текст до первого конца предложения или длины 200."""
    if not text:
        return None
    # Ищем конец предложения
    m = re.search(r"[.!?]\s", text)
    if m:
        text = text[: m.start() + 1].strip()
    if len(text) > 200:
        text = text[:200].rstrip() + "…"
    return text
