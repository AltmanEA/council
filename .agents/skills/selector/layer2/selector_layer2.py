"""Selector Layer 2 — entry-point module.

Публичный API:
    run_query(manifest_path, query, *, hints, reveal_code, audit_dir,
              call_id, repo_root) -> {output, audit, audit_path}
    validate_output_v2(output) -> list[str]

    sanitize.scrub(text) -> (cleaned, count)
    sources.resolve_doc(entry, repo_root) -> str
    code.search(repo_root, query, excluded_paths) -> list[str]

Константы:
    CONTRACT_VERSION, DEFAULT_CODE_MODE, CEILING_FILES, CEILING_TOKENS,
    DEFAULT_FILES, DEFAULT_TOKENS
"""

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

# ── Подмодули (атрибуты модуля) ───────────────────────────────────────────

from . import sanitize as _sanitize_mod
from . import sources as _sources_mod
from . import code as _code_mod
from . import evidence as _evidence_mod
from . import budget as _budget_mod
from . import contract as _contract_mod
from . import manifest as _manifest_mod

# Делаем подмодули доступными как атрибуты
sanitize = _sanitize_mod
sources = _sources_mod
code = _code_mod
evidence = _evidence_mod
budget = _budget_mod
contract = _contract_mod

# ── Константы ──────────────────────────────────────────────────────────────

CONTRACT_VERSION: str = "2.0.0"
DEFAULT_CODE_MODE: str = "off"
CEILING_FILES: int = 40
CEILING_TOKENS: int = 8000
DEFAULT_FILES: int = 20
DEFAULT_TOKENS: int = 4000

# Паттерны инъекций (совпадают с Layer 1)
_INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(previous\s+)?instructions",
    r"(?i)you\s+are\s+now",
    r"(?i)bypass\s+security",
    r"(?i)disregard\s+all\s+previous",
    r"(?i)from\s+now\s+on",
    r"(?i)you\s+must\s+(now|ignore)",
]


# ── Вспомогательные функции ────────────────────────────────────────────────

def _sha256_of(path: str) -> str:
    """SHA-256 файла."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _count_injections(text: str) -> tuple[bool, int]:
    """Подсчёт инъекционных совпадений."""
    count = 0
    for pat in _INJECTION_PATTERNS:
        count += len(re.findall(pat, text))
    return count > 0, count


def _postcondition_errors(output: dict) -> list[str]:
    """Validate the assembled output through both contract validators.

    The Layer 1 validator is picked up only when the adapter has preloaded
    ``selector_runtime``; Layer 2 validation always runs.  Errors are
    surfaced in the audit record (never silently dropped).
    """
    errors: list[str] = []
    try:
        errors.extend(_contract_mod.validate_output_v2(output))
    except Exception as exc:  # fail loud in the audit, never crash the call
        errors.append(f"Layer 2 validator error: {exc}")
    runtime_mod = sys.modules.get("selector_runtime")
    if runtime_mod is not None and hasattr(runtime_mod, "validate_output"):
        try:
            errors.extend(runtime_mod.validate_output(output))
        except Exception as exc:
            errors.append(f"Layer 1 validator error: {exc}")
    return errors


def _write_audit(
    audit_dir: str, call_id: str, audit: dict, call_id_val: str
) -> str:
    """Записать audit-файл (Markdown-формат, без payload)."""
    os.makedirs(audit_dir, exist_ok=True)
    audit_path = os.path.join(audit_dir, f"selector-{call_id_val}.md")

    lines: list[str] = []
    lines.append("# Selector audit")
    lines.append("")
    lines.append(f"call_id: {audit.get('call_id', call_id_val)}")
    lines.append(f"manifest_sha256: {audit.get('manifest_sha256', '')}")
    lines.append("")
    lines.append(f"injection_detected: {audit.get('injection_detected', False)}")
    inj_count = audit.get("injection_count")
    if inj_count is not None:
        lines.append(f"injection_count: {inj_count}")
    lines.append("")
    lines.append(f"request_intent: {audit.get('request_intent', '')}")
    lines.append(f"timestamp: {audit.get('timestamp', '')}")
    lines.append("")
    lines.append("## Searched Sources")
    for src in audit.get("searched_sources", []):
        lines.append(f"- {src}")
    lines.append("")
    lines.append("## Results")
    lines.append(f"- Documents found: {audit.get('documents_found', 0)}")
    lines.append(f"- Gaps: {audit.get('gap_description', '')}")
    lines.append("")
    lines.append("## Integrity")
    lines.append(f"- Manifest integrity: {audit.get('integrity_result', '')}")
    lines.append(f"- SHA-256 verified: {audit.get('sha256_verified', '')}")

    # ── v2 fields ────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"contract_version: {audit.get('contract_version', '')}")
    lines.append(f"form: {audit.get('form', '')}")
    lines.append("")
    lines.append("## Modes")
    modes = audit.get("modes", {})
    if isinstance(modes, dict):
        lines.append(f"- docs: {modes.get('docs', '')}")
        lines.append(f"- code: {modes.get('code', '')}")
        ep = modes.get("excluded_paths", [])
        if ep:
            lines.append(f"- excluded_paths: {', '.join(str(v) for v in ep)}")
        else:
            lines.append("- excluded_paths: (none)")
    lines.append("")
    lines.append("## Sources")
    sources = audit.get("sources", [])
    if sources:
        lines.append("| id | path | sha256 |")
        lines.append("|---|---|---|")
        for src in sources:
            if isinstance(src, dict):
                sid = src.get("id", "")
                spath = src.get("path", "")
                shasum = src.get("sha256", "")
                lines.append(f"| {sid} | {spath} | {shasum} |")
            else:
                lines.append(f"| {src} | | |")
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("## Exclusions")
    cps = audit.get("code_paths_searched", [])
    if cps:
        lines.append(f"- code_paths_searched: {', '.join(str(v) for v in cps)}")
    else:
        lines.append("- code_paths_searched: (none)")
    ep_val = modes.get("excluded_paths", []) if isinstance(modes, dict) else []
    if ep_val:
        lines.append(f"- excluded_paths: {', '.join(str(v) for v in ep_val)}")
    else:
        lines.append("- excluded_paths: (none)")

    content = "\n".join(lines)
    with open(audit_path, "w", encoding="utf-8") as f:
        f.write(content)

    return audit_path


def _rank(request: str, entries: list[dict], max_files: int) -> list[dict]:
    """Layer 1 совместимое ранжирование (детерминированное).

    Возвращает список: [{id, rank, rationale, discoverable, status}].
    """
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
        for w in words:
            if w in entry_id.lower():
                score += 10
            if w in title.lower():
                score += 5
            if w in description.lower():
                score += 3
            if w in abstraction.lower():
                score += 2
            if w in status.lower():
                score += 1

        if description:
            score += 1
            if status in ("draft", "active"):
                score += 1

        scored.append((score, entry_id, idx))

    # Детерминированная сортировка
    scored.sort(key=lambda x: (-x[0], x[1]))

    ranked = scored[:max_files]

    results: list[dict] = []
    for rank_num, (score, doc_id, idx) in enumerate(ranked, start=1):
        entry = entries[idx]
        title = entry.get("title", doc_id)
        description = entry.get("description", "")
        abstraction = entry.get("abstraction", "")
        status = entry.get("status", "")

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

        if abstraction:
            rationale_parts.append(f"Abstraction: {abstraction}.")
        if status == "draft":
            rationale_parts.append("[draft]")
        elif status == "archive":
            rationale_parts.append("[archive] Historical/non-authoritative.")

        rationale = " ".join(rationale_parts)
        discoverable = "yes" if description else "no"

        results.append({
            "id": doc_id,
            "rank": rank_num,
            "rationale": rationale,
            "discoverable": discoverable,
            "status": status,
        })

    return results


# ── Публичный API ──────────────────────────────────────────────────────────

def run_query(
    manifest_path: str,
    query: str,
    *,
    hints: dict | None = None,
    reveal_code: bool = False,
    audit_dir: str | None = None,
    call_id: str | None = None,
    repo_root: str | None = None,
) -> dict:
    """Выполнить запрос к Selector Layer 2.

    Args:
        manifest_path: Путь к YAML-файлу манифеста.
        query: Текстовый запрос пользователя.
        hints: Опциональные подсказки бюджета {max_files, max_tokens}.
        reveal_code: Включить сканирование кода (опционально).
        audit_dir: Каталог для audit-файла (None = не писать).
        call_id: Идентификатор вызова.
        repo_root: Корень репозитория (None = автоопределение).

    Returns:
        {output: dict, audit: dict, audit_path: str|None}
    """
    if call_id is None:
        call_id = uuid.uuid4().hex[:8]

    # Санитизация запроса — предотвращает инъекции в request_intent / task_summary
    clean_query, _ = _sanitize_mod.scrub(query)

    # ── 1. Загрузка манифеста ────────────────────────────────────────────
    entries, manifest_sha, raw_injected, raw_inj_count, error_text = _manifest_mod.load_manifest(
        manifest_path
    )

    # Определяем repo_root
    if repo_root is None:
        repo_root = _manifest_mod.discover_repo_root(manifest_path)

    # ── 2. Fail-closed: ошибка манифеста ─────────────────────────────────
    if error_text:
        error_kind = _manifest_mod.classify_manifest_error(error_text)
        # Any unavailable/invalid manifest is reported as "manifest_missing":
        # it is the only gap_type both validators allow with empty facts and
        # ranked_ids. The concrete reason lives in error_kind.
        gap_type = "manifest_missing"
        hint_ack = "hints not fully applied — manifest unavailable" if hints else "no hints provided; manifest unavailable"

        output = {
            "task_summary": f"Error: {error_text}",
            "manifest_sha256": manifest_sha,
            "ranked_ids": {},
            "disclaimer": "recommended starting set, not a boundary",
            "discoverable": "no",
            "interim_form": "Layer 1",
            "gap": {
                "gap_type": gap_type,
                "error_kind": error_kind,
                "searched_sources": ["docs-manifest.yaml"],
                "covered_items": [],
                "omitted_items": [],
                "excluded_paths": [],
                "code_paths_searched": [],
            },
            "hint_acknowledgement": hint_ack,
            "truncated": False,
            "contract_version": CONTRACT_VERSION,
            "form": "Layer 2",
            "facts": [],
            "sources": [],
            "modes": {
                "docs": "default",
                "code": DEFAULT_CODE_MODE,
                "excluded_paths": [],
            },
            "integrity": {
                "manifest_sha256": manifest_sha,
                "sources_verified": False,
                "injection_detected": raw_injected,
                "injection_count": raw_inj_count,
            },
        }

        audit_dict = {
            "call_id": call_id,
            "manifest_sha256": manifest_sha or "",
            "request_intent": clean_query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "searched_sources": ["docs-manifest.yaml"],
            "documents_found": 0,
            "documents_skipped": 0,
            "gap_description": gap_type,
            "error_kind": error_kind,
            "limitations": "evidence-based",
            "integrity_result": "n/a",
            "sha256_verified": "false",
            "injection_detected": raw_injected,
            "injection_count": raw_inj_count,
            "contract_version": CONTRACT_VERSION,
            "form": "Layer 2",
            "modes": {
                "docs": "default",
                "code": DEFAULT_CODE_MODE,
                "excluded_paths": [],
            },
            "sources": [],
            "code_paths_searched": [],
        }

        audit_dict["validation_errors"] = _postcondition_errors(output)

        audit_path = ""
        if audit_dir:
            audit_path = _write_audit(audit_dir, call_id, audit_dict, call_id)

        return {"output": output, "audit": audit_dict, "audit_path": audit_path}

    # ── 3. Определяем бюджет ─────────────────────────────────────────────
    eff_files, eff_tokens, exceeded_ceiling = _budget_mod.clamp_budget(hints)

    # ── 4. Фильтруем RU / archive, разрешаем источники ───────────────────
    valid_sources = _sources_mod.filter_valid_sources(entries, repo_root)
    source_ids = {s["id"] for s in valid_sources}

    # ── 5. Сканируем файлы на инъекции ──────────────────────────────────
    # Сканируем ВСЕ файлы из манифеста (не только EN)
    total_injections = raw_inj_count
    for entry in entries:
        rel_path = entry.get("path", "")
        if not rel_path:
            continue
        try:
            if os.path.isabs(rel_path):
                abs_p = rel_path
            else:
                abs_p = os.path.join(repo_root, rel_path)

            if not os.path.isfile(abs_p):
                continue

            with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

            detected, cnt = _count_injections(text)
            if detected:
                total_injections += cnt

        except Exception:
            pass

    injection_detected = total_injections > 0

    # ── 6. Код-режим ────────────────────────────────────────────────────
    code_mode = "on" if reveal_code else "off"
    code_paths: list[str] = []
    if reveal_code:
        excluded_paths = hints.get("excluded_paths", []) if hints else []
        code_paths = _code_mod.search(repo_root, query, excluded_paths)

    # ── 7. Фильтруем entries — только файлы, существующие как regular file ──
    # Documenter: если файл не существует (device, symlink, etc.) —
    # документ не попадает в ranked_ids, но остаётся в omitted_items.
    _real_entries: list[dict] = []
    for entry in entries:
        rel_path = entry.get("path", "")
        if not rel_path:
            continue
        try:
            if os.path.isabs(rel_path):
                abs_p = rel_path
            else:
                abs_p = os.path.join(repo_root, rel_path)
        except Exception:
            continue
        if os.path.isfile(abs_p):
            _real_entries.append(entry)

    # ── 8. Ранжирование (на основе существующих файлов) ─
    ranked_items = _rank(clean_query, _real_entries, eff_files)

    # ── 8. Формируем ranked_ids ──────────────────────────────────────────
    ranked_ids: dict = {}
    for item in ranked_items:
        ranked_ids[item["id"]] = item

    covered_ids = [item["id"] for item in ranked_items]
    all_doc_ids = [e.get("id", "") for e in entries]

    # ── 9. Gap ───────────────────────────────────────────────────────────
    if exceeded_ceiling:
        gap_type = "budget_stop"
        omitted_items = _budget_mod.budget_omitted_items(
            all_doc_ids, covered_ids, gap_type
        )
    elif covered_ids:
        omitted_ids = [e["id"] for e in entries if e.get("id") not in covered_ids]
        if omitted_ids:
            gap_type = "partial"
            omitted_items = omitted_ids
        else:
            gap_type = "none"
            omitted_items = []
    elif not covered_ids:
        gap_type = "not_found"
        omitted_items = all_doc_ids
    else:
        gap_type = "none"
        omitted_items = []

    # ── 10. Task summary ─────────────────────────────────────────────────
    n_covered = len(covered_ids)
    if exceeded_ceiling:
        task_summary = (
            "\u26a0 TRUNCATED \u2014 Budget ceiling reached "
            "during evidence retrieval."
        )
    else:
        task_summary = (
            f"Index-only discovery for {clean_query}: "
            f"{n_covered} relevant documents found with evidence."
        )

    # ── 11. Hints acknowledgement ────────────────────────────────────────
    if exceeded_ceiling:
        hint_ack = (
            "hints not fully applied: budget ceiling reached"
            if hints
            else "no hints provided; budget ceiling reached"
        )
    else:
        hint_ack = "hints applied" if hints else "no hints provided"

    # ── 12. Формируем sources[] ──────────────────────────────────────────
    sources_out: list[dict] = []
    for s in valid_sources:
        sources_out.append({
            "id": s["id"],
            "path": s["path"],
            "sha256": s["sha256"],
            "kind": s["kind"],
            "status": s["status"],
            "abstraction": s["abstraction"],
            "section": s.get("section", "Introduction"),
            "anchor": s.get("anchor"),
            "lines": s.get("lines"),
            "symbol": s.get("symbol"),
        })

    # Если reveal_code, добавляем code-источники
    if reveal_code:
        for cp in code_paths:
            try:
                h = hashlib.sha256()
                with open(cp, "rb") as f:
                    h.update(f.read())
                code_id = f"code-{os.path.basename(cp)}"
                sources_out.append({
                    "id": code_id,
                    "path": os.path.relpath(cp, repo_root),
                    "sha256": h.hexdigest(),
                    "kind": "code",
                    "status": "active",
                    "abstraction": "operational",
                    "section": None,
                    "lines": None,
                    "anchor": None,
                    "symbol": None,
                })
            except Exception:
                pass

    # ── 13. Формируем facts[] ────────────────────────────────────────────
    facts_out = _evidence_mod.build_facts(valid_sources, ranked_items)

    # ── 14. Формируем output ─────────────────────────────────────────────
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
            "excluded_paths": hints.get("excluded_paths", []) if hints else [],
            "code_paths_searched": code_paths,
        },
        "hint_acknowledgement": hint_ack,
        "truncated": exceeded_ceiling,
        "contract_version": CONTRACT_VERSION,
        "form": "Layer 2",
        "facts": facts_out,
        "sources": sources_out,
        "modes": {
            "docs": "default",
            "code": code_mode,
            "excluded_paths": hints.get("excluded_paths", []) if hints else [],
        },
        "integrity": {
            "manifest_sha256": manifest_sha,
            "sources_verified": len(valid_sources) > 0 and not injection_detected,
            "injection_detected": injection_detected,
            "injection_count": total_injections,
        },
    }

    # ── 15. Формируем audit ──────────────────────────────────────────────
    sources_for_audit: list[dict] = []
    for s in valid_sources:
        sources_for_audit.append({
            "id": s["id"],
            "path": s["path"],
            "sha256": s["sha256"],
        })

    audit_dict = {
        "call_id": call_id,
        "manifest_sha256": manifest_sha,
        "request_intent": clean_query,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "searched_sources": ["docs-manifest.yaml"],
        "documents_found": n_covered,
        "documents_skipped": len(all_doc_ids) - n_covered,
        "gap_description": gap_type,
        "limitations": "evidence-based",
        "integrity_result": "ok" if not injection_detected else "warnings",
        "sha256_verified": "true" if valid_sources else "false",
        "injection_detected": injection_detected,
        "injection_count": total_injections,
        "contract_version": CONTRACT_VERSION,
        "form": "Layer 2",
        "modes": {
            "docs": "default",
            "code": code_mode,
            "excluded_paths": hints.get("excluded_paths", []) if hints else [],
        },
        "sources": sources_for_audit,
        "code_paths_searched": code_paths,
    }

    # ── 16. Postcondition + пишем audit ──────────────────────────────────
    audit_dict["validation_errors"] = _postcondition_errors(output)

    audit_path = ""
    if audit_dir:
        audit_path = _write_audit(audit_dir, call_id, audit_dict, call_id)

    return {
        "output": output,
        "audit": audit_dict,
        "audit_path": audit_path,
    }


# ── Alias для backcompat ──────────────────────────────────────────────────

validate_output_v2 = _contract_mod.validate_output_v2
