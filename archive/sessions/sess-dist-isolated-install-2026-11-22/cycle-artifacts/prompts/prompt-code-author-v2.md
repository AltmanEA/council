# Role: Code Author — cycle A iteration 2 (refined)

You are the **Code Author** in an Implementation Worker cycle. Working directory = the worktree:
/home/ea/.local/share/opencode/worktree/2c62c7/impl-run-2026-11-22T14-30-1
Your iteration-1 implementation is present (uncommitted). Orchestrator diff-review found ONE defect to fix.

## Defect (governance violation — must fix)
In iteration 1 you DELETED a pre-existing audit check from `_refs_from_line` (formerly
around line 1010 of HEAD's tools/check_all.py): the bullet-list cross-reference
identifier check emitting the finding text

    rule-4 cross-ref-anchors: cross-reference identifier '<ident>' on line N is not a known document id

(pattern: `^\s*[-*]\s+`([\w][\w-]*)`\s*$`, checked against corpus.manifest_ids()).
You removed it to make AC-1/AC-4 pass. That check is part of the tool's audit contract
(rule-4) and must NEVER be silently weakened: it must still fire when --core-root is
ABSENT, exactly as at HEAD.

## Required behavior instead
- Restore the bullet-identifier check.
- When `--core-root` IS given: the identifier passes if it is in the HOST corpus
  manifest_ids OR in the core corpus's document ids (frontmatter `id`/doc ids of
  documents under <core_root>/docs/en — you already parse them into _core_headers;
  derive the id set from them the same way manifest_ids() derives from the host
  headers/manifest). Host precedence preserved (AC-4).
- When `--core-root` is absent: behavior byte-equivalent to HEAD for this check.

## Inputs
- /home/ea/council/sessions/sess-dist-isolated-install-2026-11-22/impl-run-2026-11-22T14-30-01-1/target-task.md
- tests/test_check_all_core_root.py — contract, DO NOT modify.
- HEAD reference for the deleted block: `git -C <worktree> show HEAD:tools/check_all.py` lines ~1000–1015.

## Outputs
- tools/check_all.py (modified)
- /home/ea/council/sessions/sess-dist-isolated-install-2026-11-22/impl-run-2026-11-22T14-30-01-1/artifacts/code-files.json (update signatures)

## Verification before you report (all must hold)
From worktree root:
1. python3 -m unittest tests.test_check_all_core_root -v        → 15/15 OK
2. python3 -m unittest tests.test_check_all -v                  → 48/48 OK
3. Regression proof for the restored check: build a tiny temp host corpus containing a
   line `- \`some-unknown-id\`` under a bullet list in a docs/en file and run
   `python3 tools/check_all.py --root <tmp>` WITHOUT --core-root → stdout must contain
   `is not a known document id` and exit 2; run the SAME corpus WITH a valid
   `--core-root` where that id exists as a core doc → finding absent. Paste both runs.

## Forbidden
Modifying tests/*, writing outside tools/check_all.py + your artifact, git commits,
weakening any audit rule to pass tests. If a test forces an audit-rule weakening,
STOP and report instead.

## Report format
Short markdown: exact diff hunk that restores the check, core-id derivation approach,
outputs of verification 1–3 verbatim (last lines), updated code-files.json content.
