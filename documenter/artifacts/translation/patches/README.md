# Vendored engine patches (documented local deviations)

Local, tracked patches applied to `vendor/techdoc-translator/` beyond the
pinned release in `defaults/translation.lock`. Each patch here records the
exact working-tree diff; the vendored tree MUST match it byte-for-byte
(verified by `tools/check_vendor.py`). This is an exception mechanism, not
the normal path: the normal path is an upstream release plus
`tools/sync_translator.sh` (AGENTS.md §1.7, ADR-014).

## glossary-list-parser.patch

- Base: `v0.1.0` / commit `0b48ad9` (the current lock pin).
- Files touched: `techdoc_translator.py`, `tests/test_unit.py`, `README.md`,
  `SHA256SUMS` (the vendor's own checksums updated to match the patch).
- Fixes upstream bug: `load_glossary` anchored on bare `**Term** (рус.)`
  lines and parsed **0 terms silently** from bulleted host glossaries —
  no warning, no nonzero exit ("0 terms молча", host audit G-1/E-2).
- Behavior after patch: entry lines may carry a markdown list marker
  (`- `, `* `, `+ `) before the bolded term; unit tests added upstream-style
  in `tests/test_unit.py` (29 tests pass).
- Consumer-side counterpart: `tools/check_drift.py::parse_glossary_terms`
  accepts the same formats (shared contract, commit c62481a).
- Superseded when: the Translation Project ships an upstream release with
  the list-format fix (Translation Project analysis item 7). Then run
  `tools/sync_translator.sh` from that release, delete this patch file and
  the annotation in `defaults/translation.lock`.
- Do not let `sync_translator.sh` run over the patched tree without this
  record: the script replaces `vendor/` wholesale and silently drops the
  patch; `tools/check_vendor.py` flags such drift as a finding.
