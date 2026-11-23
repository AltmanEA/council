# Role: Test Author — impl-run-2026-11-19T14-30-02, iteration 3 (ONE FIX, zero-trust)

Продолжение. Оператор продолжил цикл после governance-остановки. Ты в итерации 2 ОСЛАБИЛ
live-тест (skipTest) — это green-washing acceptance-критерия. Возвращаешь его к жёсткой
форме. Точечная правка, никакой инициативы.

## ZERO-TRUST (нарушение = задача ПРОВАЛЕНА)
- Разрешён к изменению РОВНО ОДИН файл: `tests/test_check_drift.py`.
- ЛЮБОЙ изменённый путь вне него (tools/**, docs/**, docs-manifest.yaml, CHANGELOGS/**,
  fixtures, .agents/**) = ПРОВАЛ. НЕ трогай — доложи в отчёте.
- Запрещено: ослаблять assertions ради зелёного прогона; добавлять skipTest/skipUnless для
  реальных (не окруженческих) отказов. skipUnless допустим ТОЛЬКО для отсутствия файлов
  окружения (EN/RU corpus absent), НЕ для «known issues».
- НЕ меняй tools/ (Code Author параллельно правит stem-4). НЕ коммить.

## Правка (тест test_live_documenter_service, ~строки 510-535)
Убери условный skip. Жёсткая форма:
```python
    @unittest.skipUnless(
        os.path.exists(os.path.join(WORKTREE, "docs", "ru", "documenter-service", "index-RU.md"))
        and os.path.exists(os.path.join(WORKTREE, "docs", "en", "documenter-service", "index.md")),
        "No live EN/RU corpus for live test",
    )
    def test_live_documenter_service(self):
        """Real corpus: check_drift --phase4 on documenter-service EN/RU must exit 0."""
        en_path = os.path.join(WORKTREE, "docs", "en", "documenter-service", "index.md")
        ru_path = os.path.join(WORKTREE, "docs", "ru", "documenter-service", "index-RU.md")
        rc, out, err = _run_cli(
            "--phase4", en_path, ru_path,
            "--report", os.path.join(FIXTURES_DIR, "report_fail0.json"),
            "--glossary", os.path.join(WORKTREE, "docs", "en", "glossary", "index.md"),
        )
        self.assertEqual(rc, 0, f"Live corpus failed: {out}\n{err}")
        self.assertNotIn("rule=phase4-", out)
```
Удали строку(и) `if "phase4-parity" in out ...: self.skipTest(...)`. Проверь также
условный skipTest на строке ~194 («phase4 not yet implemented»): это анти-reversed-TDD
костыль — если --phase4 теперь реализован, удали и его (тест обязан выполняться).

## Самопроверка
`cd WORKTREE && python3 -m unittest tests.test_check_drift -v` → все живые тесты
ВЫПОЛНЯЮТСЯ (skips только по отсутствию окружения). После stem-4 от Code Author live-тест
зелёный; если Code Author ещё не применил — live-тест будет КРАСНЫЙ, это ОЖИДАЕМО и
правильно (не ослабляй!). Зафиксируй counts в .impl/artifacts/test-files.json.

## Формат отчёта
Что удалено/изменено; counts (passed/failed/skipped) с пояснением по каждому skip.
