"""Budget management for Layer 2.

Enforces ``CEILING_FILES`` and ``CEILING_TOKENS`` limits.  When ``hints``
exceed the ceiling, the query is marked ``truncated`` and ``gap_type``
becomes ``budget_stop``.
"""

import math

# ---------------------------------------------------------------------------
# Константы (совпадают с Layer 1)
# ---------------------------------------------------------------------------

CEILING_FILES: int = 40
CEILING_TOKENS: int = 8000
DEFAULT_FILES: int = 20
DEFAULT_TOKENS: int = 4000


def clamp_budget(hints: dict | None = None) -> tuple[int, int, bool]:
    """Определить эффективный бюджет из hints.

    Args:
        hints: {max_files, max_tokens} — опциональные подсказки.

    Returns:
        (effective_max_files, effective_max_tokens, exceeded_ceiling).

    Если hints превышают ceiling — exceeded_ceiling=True, и эффективный
    бюджет приравнивается к ceiling.
    """
    if hints:
        max_files = hints.get("max_files", DEFAULT_FILES)
        max_tokens = hints.get("max_tokens", DEFAULT_TOKENS)
    else:
        max_files = DEFAULT_FILES
        max_tokens = DEFAULT_TOKENS

    exceeded = bool(
        hints and (max_files > CEILING_FILES or max_tokens > CEILING_TOKENS)
    )

    effective_files = min(max_files, CEILING_FILES)
    effective_tokens = min(max_tokens, CEILING_TOKENS)

    return effective_files, effective_tokens, exceeded


def budget_omitted_items(
    all_ids: list[str], covered_ids: list[str], gap_type: str
) -> list[str]:
    """Сформировать список пропущенных элементов из-за бюджета.

    Args:
        all_ids: Все идентификаторы документов.
        covered_ids: Идентификаторы, вошедшие в output.
        gap_type: Тип разрыва.

    Returns:
        Список строк с описаниями пропущенных элементов.
    """
    omitted = [eid for eid in all_ids if eid not in covered_ids]
    if gap_type == "budget_stop":
        return [f"{eid} (budget ceiling reached)" for eid in omitted]
    return omitted
