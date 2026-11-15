#!/usr/bin/env python3
"""Document header (frontmatter) parser and validator for Council docs.

Pure functions only: stdlib + PyYAML, no side effects, no filesystem writes.
Canonical header format (documentation-rules §2.2, configuration-guide §Manifest Field
Provenance): first `# ` H1 line, then a contiguous block of `Key: value`
lines (no blank lines inside the block) parseable via yaml.safe_load as a
single mapping. Blank lines between H1 and the block are tolerated.

Recognized keys: id, title, Version, Status, Abstraction, has_translation,
references (YAML flow list), allow_non_index_paths (bool), changelog-path.
Unknown keys are tolerated but reported as low findings; `Last Modified` is
tolerated but reported as a deprecated warning. NEVER silent-skip.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import yaml

__all__ = [
    "DocMetaError",
    "HeaderData",
    "REQUIRED_KEYS",
    "KNOWN_KEYS",
    "parse_header",
    "validate",
]

#: Required frontmatter keys (missing any of these is a parse error).
REQUIRED_KEYS = ("id", "Version", "Status", "Abstraction", "changelog-path")

#: Recognized frontmatter keys; anything else is an unknown-key finding.
KNOWN_KEYS = REQUIRED_KEYS + (
    "title",
    "has_translation",
    "references",
    "allow_non_index_paths",
    "Last Modified",
)

_VERSION_RE = re.compile(r"^\d+(\.\d+){0,2}(-draft)?$")


class DocMetaError(Exception):
    """Fatal header parse error for ``filename`` with human-readable ``reason``."""

    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(f"{filename}: {reason}")
        self.filename = filename
        self.reason = reason


@dataclass
class HeaderData:
    """Parsed canonical document header.

    h1_title: text of the first `# ` heading (always present on success).
    fields:   mapping of frontmatter key -> parsed value (strings, bools, lists).
    warnings: free-form non-fatal notes collected during parsing.
    """

    h1_title: str
    fields: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def _normalize_value(value):
    """Coerce YAML-parsed scalars: dates (e.g. Last Modified) -> ISO strings."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_value(v) for v in value]
    return value


def parse_header(text: str, filename: str = "<string>") -> HeaderData:
    """Parse a canonical document header from ``text``.

    Returns HeaderData on success. Raises DocMetaError when: no H1 line is
    found, the metadata block is missing/unparsable/not a mapping, or any
    required key (id, Version, Status, Abstraction, changelog-path) is absent.
    """
    lines = text.splitlines()

    h1_index = None
    h1_title = None
    for i, line in enumerate(lines):
        if line.startswith("# "):
            h1_index = i
            h1_title = line[2:].strip()
            break
    if h1_index is None:
        raise DocMetaError(filename, "no H1 heading (`# ` title line) found")

    # Metadata block: skip blank lines after H1, then take a contiguous
    # run of non-blank lines (no blank lines inside the block).
    i = h1_index + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    block_start = i
    while i < len(lines) and lines[i].strip():
        i += 1
    block_lines = lines[block_start:i]

    if not block_lines:
        missing = ", ".join(REQUIRED_KEYS)
        raise DocMetaError(filename, f"missing required key(s): {missing} (empty metadata block)")

    block_text = "\n".join(block_lines)
    try:
        data = yaml.safe_load(block_text)
    except yaml.YAMLError as exc:
        raise DocMetaError(filename, f"unparsable YAML metadata block: {exc}") from exc

    if data is None or not isinstance(data, dict):
        raise DocMetaError(filename, "metadata block is not a YAML mapping")

    fields = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise DocMetaError(filename, f"non-string metadata key: {key!r}")
        fields[key] = _normalize_value(value)

    warnings: list = []
    missing = [k for k in REQUIRED_KEYS if k not in fields or fields[k] in (None, "")]
    if missing:
        raise DocMetaError(filename, "missing required key(s): " + ", ".join(missing))

    return HeaderData(h1_title=h1_title, fields=fields, warnings=warnings)


def _finding(rule: str, severity: str, file: str, description: str) -> dict:
    return {"rule": rule, "severity": severity, "file": file, "description": description}


def validate(header: HeaderData, file: str = "<unknown>", root: str = ".") -> list:
    """Validate a parsed header; returns a list of finding dicts.

    Each finding: {rule, severity (high|medium|low|warning), file, description}.
    Never raises for content problems — only reports. ``file`` is the
    repository-relative document path; ``root`` anchors changelog-path checks.
    """
    findings: list = []
    fields = header.fields

    # Required-field checks (defensive: parse_header already enforces these).
    for key in REQUIRED_KEYS:
        if key not in fields or fields[key] in (None, ""):
            findings.append(_finding(
                "required-field", "high", file, f"required frontmatter key missing: {key}"))

    # Version format: (X|X.Y|X.Y.Z)(-draft)?
    version = fields.get("Version")
    if version is not None and not _VERSION_RE.match(str(version)):
        findings.append(_finding(
            "version-format", "high", file,
            f"Version {version!r} does not match (X|X.Y|X.Y.Z)(-draft)?"))

    # changelog-path: must live under CHANGELOGS/ and exist on disk.
    cl = fields.get("changelog-path")
    if isinstance(cl, str) and cl:
        if not cl.replace("\\", "/").startswith("CHANGELOGS/"):
            findings.append(_finding(
                "changelog-path-location", "medium", file,
                f"changelog-path {cl!r} does not point under CHANGELOGS/"))
        if not os.path.isfile(os.path.join(root, *cl.replace("\\", "/").split("/"))):
            findings.append(_finding(
                "changelog-path-missing", "high", file,
                f"changelog-path {cl!r} does not resolve to an existing file under {root}"))

    # references: non-empty targets allowed only when allow_non_index_paths
    # is true OR the file is the canonical docs/en/<id>/index.md (documentation-rules §2.1
    # multi-doc exception rule).
    refs = fields.get("references")
    if refs:
        allowed = fields.get("allow_non_index_paths") is True
        doc_id = fields.get("id")
        is_canonical_index = isinstance(doc_id, str) and file.replace("\\", "/") == f"docs/en/{doc_id}/index.md"
        if not allowed and not is_canonical_index:
            findings.append(_finding(
                "references-non-index", "high", file,
                "non-empty references requires allow_non_index_paths: true unless the "
                f"file is the canonical docs/en/{doc_id}/index.md (documentation-rules §2.1)"))

    # Unknown keys: tolerated, reported low. Last Modified: deprecated warning.
    for key in fields:
        if key == "Last Modified":
            findings.append(_finding(
                "last-modified-deprecated", "warning", file,
                "`Last Modified` field is deprecated (derived from git; remove it)"))
        elif key not in KNOWN_KEYS:
            findings.append(_finding(
                "unknown-key", "low", file, f"unknown frontmatter key: {key!r}"))

    return findings
