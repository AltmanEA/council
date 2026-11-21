"""Injection sanitisation for Layer 2.

``scrub(text)`` — удаляет инъекционные паттерны из текста и возвращает
очищенный текст + счётчик удалений.

Паттерны (case-insensitive):
  - ``IGNORE PREVIOUS INSTRUCTIONS``
  - ``you are now``
  - ``bypass security``
  - ``disregard all previous``
  - ``from now on``
  - ``you must now|ignore``
"""

import re


_INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(previous\s+)?instructions",
    r"(?i)you\s+are\s+now",
    r"(?i)bypass\s+security",
    r"(?i)disregard\s+all\s+previous",
    r"(?i)from\s+now\s+on",
    r"(?i)you\s+must\s+(now|ignore)",
]


def scrub(text: str) -> tuple[str, int]:
    """Удалить инъекционные паттерны из текста.

    Args:
        text: Исходный текст (тело документа, комментарий кода и т.д.).

    Returns:
        Кортеж (очищенный_текст, счётчик_удалений).
    """
    count = 0
    cleaned = text
    for pat in _INJECTION_PATTERNS:
        matches = re.findall(pat, cleaned)
        count += len(matches)
        if matches:
            cleaned = re.sub(pat, "", cleaned)
    return cleaned, count


def detect_injections(text: str) -> tuple[bool, int]:
    """Быстрая проверка на наличие инъекций (без удаления).

    Args:
        text: Текст для проверки.

    Returns:
        (detected, count).
    """
    count = 0
    for pat in _INJECTION_PATTERNS:
        count += len(re.findall(pat, text))
    return count > 0, count
