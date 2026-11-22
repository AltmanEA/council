#!/usr/bin/env python3
"""remap_host_paths.py — build-time host path remapping for the dist channel.

The source repo's AGENTS.md and the shipped Documentation Worker / Selector
skills describe the SOURCE-REPO layout: tools live under ``tools/``, framework
docs under ``docs/en/<id>/``, skills under ``.agents/skills/``.  On a host the
whole framework is isolated under ``.council/`` (consensus
``sess-dist-isolated-install-2026-11-22``), so those paths do not resolve and
agents end up "missing" ``tools/`` and ``docs/en/documentation-rules/``.

This script rewrites the staged copies (AGENTS.md.template and the shipped
skill SKILL.md files) so every FRAMEWORK path carries the ``.council/``
prefix and every audit/manifest command carries explicit dual-root flags.
HOST-OWNED paths deliberately stay at the host root and are NOT prefixed:
host ``docs/en/<id>/`` documents (except the shipped framework IDs), root
``docs-manifest.yaml``, ``CHANGELOGS/``, ``documenter/`` translation
provenance (the tools write them CWD-relative).

Usage: python3 remap_host_paths.py <file> [<file> ...] [--host-note AGENTS]

Idempotent: already-prefixed paths are not double-prefixed (negative
lookbehind on the framework-root tokens).
"""
import re
import sys

# Framework docs shipped into .council/docs/en/ (build.sh copy_core list).
# Only these ids get the prefix; host-authored docs/en/<id>/ stays at root.
FRAMEWORK_DOC_IDS = (
    "documentation-rules",
    "documenter-service",
    "translation-project",
    "protocol-core",
    "glossary",
    "archive",
)

# Command forms that need explicit flags because the tools' default --root
# is the parent of the script (= .council/ on a host), which would audit or
# rewrite the CORE corpus instead of the host corpus.
COMMAND_REWRITES = [
    (re.compile(r"python3 tools/check_all\.py\b"),
     "python3 .council/tools/check_all.py --root . --core-root .council"),
    (re.compile(r"python3 tools/gen_manifest\.py (?=--write|--check)"),
     "python3 .council/tools/gen_manifest.py --root . "),
    (re.compile(r"python3 tools/bump_version\.py\b"),
     "python3 .council/tools/bump_version.py --root ."),
    (re.compile(r"python3 tools/classify_bump\.py\b"),
     "python3 .council/tools/classify_bump.py --root ."),
]

# Generic framework-root tokens.  (?<![\w./-]) keeps already-prefixed
# occurrences (.council/tools/) untouched and avoids matching inside words.
GENERIC_REWRITES = [
    (re.compile(r"(?<![\w./-])/?\.agents/skills/"), ".council/skills/"),
    (re.compile(r"(?<![\w./-])tools/"), ".council/tools/"),
    (re.compile(r"(?<![\w./-])(docs/en/(?:%s)\b)"
                % "|".join(FRAMEWORK_DOC_IDS)), r".council/\1"),
    (re.compile(r"(?<![\w./-])defaults/"), ".council/defaults/"),
    (re.compile(r"(?<![\w./-])fallback/"), ".council/fallback/"),
    (re.compile(r"(?<![\w./-])vendor/techdoc-translator/"),
     ".council/vendor/techdoc-translator/"),
]

# One prose clarification: translation.lock's local_path is relative to the
# framework root, not the host root.
SPECIFIC_REWRITES = [
    (re.compile(r"`local_path` points to the vendored distribution"),
     "`local_path` resolves against the framework root (`.council/`) and "
     "points to the vendored distribution"),
]

HOST_NOTE = """
---

## Host layout note (dist install)

The Council framework is isolated under `.council/` (consensus
`sess-dist-isolated-install-2026-11-22`): every `tools/`, framework
`docs/en/<framework-id>/`, `.agents/skills/` and `defaults/` path in this
file resolves under `.council/` (e.g. `.council/tools/check_all.py`,
`.council/docs/en/documentation-rules/index.md`). Host-owned paths stay at
the host root: your own `docs/en/<your-id>/` documents, the root
`docs-manifest.yaml`, `CHANGELOGS/`, and `documenter/` translation
provenance. Because the tools' default `--root` is the parent of their own
location (`.council/`), always pass explicit roots for host work:
`python3 .council/tools/check_all.py --root . --core-root .council` and
`python3 .council/tools/gen_manifest.py --root . --write`.
"""


def remap(text: str) -> str:
    for pat, repl in COMMAND_REWRITES:
        text = pat.sub(repl, text)
    for pat, repl in SPECIFIC_REWRITES:
        text = pat.sub(repl, text)
    for pat, repl in GENERIC_REWRITES:
        text = pat.sub(repl, text)
    return text


def main(argv):
    files = [a for a in argv if not a.startswith("--")]
    host_note = "--host-note" in argv
    if not files:
        print("usage: remap_host_paths.py <file>... [--host-note]", file=sys.stderr)
        return 2
    for path in files:
        with open(path, encoding="utf-8") as f:
            original = f.read()
        updated = remap(original)
        if host_note and "Host layout note (dist install)" not in updated:
            updated = updated.rstrip("\n") + "\n" + HOST_NOTE
        if updated != original:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            print(f"  [transform] host path remap: {path}")
        else:
            print(f"  [transform] host path remap: {path} (no changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
