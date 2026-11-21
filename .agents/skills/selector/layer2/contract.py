"""Validation of Layer 2 output structure.

``validate_output_v2(output) -> list[str]`` — проверяет выход Layer 2
на соответствие контракту v2. Возвращает пустой список при валидности,
список строк-ошибок в противном случае.

Проверяет:
  - 9 legacy-полей (task_summary, ranked_ids, disclaimer, discoverable,
    interim_form, gap, hint_acknowledgement, truncated, manifest_sha256).
  - 6 новых полей Layer 2 (contract_version, form, facts, sources, modes, integrity).
  - Константные значения (contract_version="2.0.0", form="Layer 2").
  - Структуру facts (каждый факт имеет claim, sources[], status; sources[] не пуст).
  - Структуру sources (id, path, sha256, kind, status, abstraction).
  - Структуру gap (core + L2 additive keys).
  - Структуру modes (docs, code, excluded_paths).
  - Структуру integrity (manifest_sha256, sources_verified, injection_detected, injection_count).
  - Правила пустого facts (допустимо только при gap_type ∈ {not_found, manifest_missing, scope_limited}).
"""

_PERMITTED_EMPTY_GAPS = {"not_found", "manifest_missing", "scope_limited"}

_REQUIRED_TOP_L2: list[str] = [
    "task_summary",
    "ranked_ids",
    "disclaimer",
    "discoverable",
    "interim_form",
    "gap",
    "hint_acknowledgement",
    "truncated",
    "manifest_sha256",
    "contract_version",
    "form",
    "facts",
    "sources",
    "modes",
    "integrity",
]

_REQUIRED_GAP_KEYS: list[str] = [
    "gap_type",
    "searched_sources",
    "covered_items",
    "omitted_items",
    "excluded_paths",
    "code_paths_searched",
]

REQUIRED_FACT_KEYS: list[str] = ["claim", "sources", "status"]
REQUIRED_SOURCE_KEYS: list[str] = ["id", "path", "sha256", "kind", "status", "abstraction"]
REQUIRED_MODES_KEYS: list[str] = ["docs", "code", "excluded_paths"]
REQUIRED_INTEGRITY_KEYS: list[str] = [
    "manifest_sha256",
    "sources_verified",
    "injection_detected",
    "injection_count",
]


def validate_output_v2(output: dict) -> list[str]:
    """Проверить вывод Layer 2 на соответствие контракту v2.

    Args:
        output: Словарь выхода из ``run_query``.

    Returns:
        Список строк с ошибками (пустой = валидно).
    """
    errors: list[str] = []

    # --- 15 top-level fields ---
    for key in _REQUIRED_TOP_L2:
        if key not in output:
            errors.append(f"Missing required field: {key!r}")

    # --- Const values ---
    if output.get("contract_version") != "2.0.0":
        errors.append(
            f"contract_version must be '2.0.0', got {output.get('contract_version')!r}"
        )
    if output.get("form") != "Layer 2":
        errors.append(
            f"form must be 'Layer 2', got {output.get('form')!r}"
        )
    if output.get("interim_form") != "Layer 1":
        errors.append(
            f"interim_form must be 'Layer 1' (legacy), got {output.get('interim_form')!r}"
        )

    # --- ranked_ids ---
    ranked_ids = output.get("ranked_ids")
    if not isinstance(ranked_ids, dict):
        errors.append("ranked_ids must be a dict")
    else:
        for doc_id, item in ranked_ids.items():
            if not isinstance(item, dict):
                errors.append(f"ranked_ids[{doc_id!r}] must be an object")
                continue
            for key in ("id", "rank", "discoverable", "status"):
                if key not in item:
                    errors.append(f"ranked_ids[{doc_id!r}] missing key: {key!r}")

    # --- gap ---
    gap = output.get("gap")
    if not isinstance(gap, dict):
        errors.append("gap must be an object")
    else:
        for key in _REQUIRED_GAP_KEYS:
            if key not in gap:
                errors.append(f"gap missing key: {key!r}")

    gap_type = gap.get("gap_type", "") if isinstance(gap, dict) else ""

    # --- facts ---
    facts = output.get("facts")
    if not isinstance(facts, list):
        errors.append("facts must be an array")
    else:
        for i, fact in enumerate(facts):
            if not isinstance(fact, dict):
                errors.append(f"facts[{i}] must be an object")
                continue
            for key in REQUIRED_FACT_KEYS:
                if key not in fact:
                    errors.append(f"facts[{i}] missing key: {key!r}")
            fact_sources = fact.get("sources", [])
            if not isinstance(fact_sources, list) or len(fact_sources) == 0:
                errors.append(f"facts[{i}] sources must be non-empty")

        # Пустые facts допустимы только при разрешённых gap_type
        if len(facts) == 0 and gap_type not in _PERMITTED_EMPTY_GAPS:
            errors.append(
                f"Empty facts not allowed for gap_type={gap_type!r}"
                f" (permitted: {sorted(_PERMITTED_EMPTY_GAPS)})"
            )

    # --- sources ---
    sources = output.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be an array")
    else:
        source_ids = set()
        for i, src in enumerate(sources):
            if not isinstance(src, dict):
                errors.append(f"sources[{i}] must be an object")
                continue
            for key in REQUIRED_SOURCE_KEYS:
                if key not in src:
                    errors.append(f"sources[{i}] missing key: {key!r}")
            source_ids.add(src.get("id", ""))

        # Проверяем, что все fact sources есть в sources[]
        for i, fact in enumerate(facts or []):
            if not isinstance(fact, dict):
                continue
            for src_id in fact.get("sources", []):
                if src_id not in source_ids:
                    errors.append(
                        f"fact[{i}] references source {src_id!r} "
                        f"not present in sources[]"
                    )

    # --- modes ---
    modes = output.get("modes")
    if not isinstance(modes, dict):
        errors.append("modes must be an object")
    else:
        for key in REQUIRED_MODES_KEYS:
            if key not in modes:
                errors.append(f"modes missing key: {key!r}")

    # --- integrity ---
    integrity = output.get("integrity")
    if not isinstance(integrity, dict):
        errors.append("integrity must be an object")
    else:
        for key in REQUIRED_INTEGRITY_KEYS:
            if key not in integrity:
                errors.append(f"integrity missing key: {key!r}")

    return errors
