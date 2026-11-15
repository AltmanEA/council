#!/usr/bin/env python3
"""translation_status.py — deterministic rebuild of translation provenance artifacts.

ADR-014 (sess-translation-extraction, 2026-11-15). Rebuilds, from stored run
reports under documenter/artifacts/translation/runs/, the per-document sidecar
(documenter/artifacts/translation/<target_id>.json) and the aggregated status
index (documenter/artifacts/translation/STATUS.md).

Inputs:
  * run reports: documenter/artifacts/translation/runs/<target_id>-<ts>.json
    (report schema: docs/en/translation-project/contract.md; one report per run;
    latest timestamp per target wins).
  * docs-manifest.yaml entries with has_translation (via gen_manifest.build_entries).
  * EN content hash (sha256) recomputed from disk for drift detection.

Status rules (Status Index glossary term):
  verified    latest report exit_code == 0 AND its output_sha256 matches the
              on-disk RU file AND the current EN sha256 matches the report's
              source_sha256
  drift       EN on disk changed since the report was made
  unverified  latest report exit_code == 0 but RU bytes do not match output_sha256
  error-<c>   latest report exit_code == c (c != 0)
  missing     no run report for a manifest-declared translation

Idempotent; writes atomically (temp+rename). Exit: 0 ok, 1 invalid input,
2 no reports directory and no sidecars (nothing to do).
"""

import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_manifest  # noqa: E402

ART_DIR = os.path.join("documenter", "artifacts", "translation")
RUNS_DIR = os.path.join(ART_DIR, "runs")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def norm_sha(value):
    return value.removeprefix("sha256:") if isinstance(value, str) else value


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_reports():
    """Return {target_id: (timestamp, report_dict)} keeping the latest per target."""
    latest = {}
    if not os.path.isdir(RUNS_DIR):
        return latest
    for name in sorted(os.listdir(RUNS_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(RUNS_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                rep = json.load(f)
            tid = rep.get("target_id") or _match_target(name)
            ts = rep.get("timestamp", "")
            if tid and (tid not in latest or ts >= latest[tid][0]):
                latest[tid] = (ts, rep)
        except (json.JSONDecodeError, OSError):
            continue  # unreadable report: skip, surfaces as missing/unverified
    return latest


_KNOWN_IDS = None


def _match_target(filename):
    """Derive target_id from <target_id>-<timestamp>.json for ids containing dashes:
    longest known manifest id that prefixes the filename."""
    global _KNOWN_IDS
    if _KNOWN_IDS is None:
        _KNOWN_IDS = sorted((t for t, _, _ in manifest_translations()),
                            key=len, reverse=True)
    stem = filename[:-5] if filename.endswith(".json") else filename
    for tid in _KNOWN_IDS:
        if stem == tid or stem.startswith(tid + "-"):
            return tid
    return None


def manifest_translations():
    """Yield (target_id, en_path, ru_path) from generated manifest entries."""
    entries, errors = gen_manifest.build_entries(".")
    if errors:
        print("[error] frontmatter parse errors: " + "; ".join(errors),
              file=sys.stderr)
    for e in entries:
        if e.get("has_translation"):
            yield e["id"], e.get("path", ""), e["has_translation"]


def compute_status(tid, en_path, ru_path, report):
    if report is None:
        return "missing", {}
    code = report.get("exit_code")
    if code != 0:
        return f"error-{code}", {}
    try:
        en_now = sha256_file(en_path)
    except OSError:
        return "drift", {}
    if norm_sha(en_now) != norm_sha(report.get("source_sha256")):
        return "drift", {"note": "EN changed after translation"}
    try:
        ru_now = sha256_file(ru_path)
    except OSError:
        return "unverified", {"note": "RU file absent"}
    if norm_sha(ru_now) != norm_sha(report.get("output_sha256")):
        return "unverified", {"note": "RU bytes differ from run output"}
    return "verified", {}


def main(argv):
    reports = load_reports()
    rows = []
    for tid, en_path, ru_path in manifest_translations():
        ts, rep = reports.get(tid, ("", None))
        status, extra = compute_status(tid, en_path, ru_path, rep)
        sidecar = dict(rep) if rep else {}
        sidecar.update({
            "target_id": tid,
            "ru_path": ru_path,
            "en_sha256_at_commit": (rep or {}).get("source_sha256"),
            "status": status,
        })
        if extra:
            sidecar.update(extra)
        atomic_write(os.path.join(ART_DIR, f"{tid}.json"),
                     json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n")
        rows.append((tid, status, sidecar))
    if not rows:
        print("[skip] no manifest translations and no reports; nothing to do")
        return 2
    lines = [
        "<!-- GENERATED by tools/translation_status.py — do not edit. "
        "Rebuild: python3 tools/translation_status.py -->",
        "",
        "# Translation Status Index",
        "",
        "| id | status | model | prompt_version | timestamp | report_ref |",
        "|---|---|---|---|---|---|",
    ]
    for tid, status, sc in sorted(rows):
        lines.append("| {} | {} | {} | {} | {} | runs/ |".format(
            tid, status, sc.get("model", ""), sc.get("prompt_version", ""),
            sc.get("timestamp", "")))
    atomic_write(os.path.join(ART_DIR, "STATUS.md"), "\n".join(lines) + "\n")
    counts = {}
    for _, status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    print(f"[ok] STATUS.md + {len(rows)} sidecar(s); statuses: "
          + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
