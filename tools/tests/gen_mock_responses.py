#!/usr/bin/env python3
"""Generate responses.json for mock translation backend.

Uses local_translate.py's exact block splitter, glossary loading, and
prompt-building logic to compute SHA256(user_prompt) keys.
"""
import hashlib
import json
import os
import sys


def main():
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    fixtures_dir = os.path.join(tests_dir, 'fixtures')
    repo_dir = os.path.dirname(os.path.dirname(tests_dir))

    # Add tools/ to sys.path so we can import local_translate
    tools_dir = os.path.dirname(tests_dir)
    sys.path.insert(0, tools_dir)

    source_path = os.path.join(fixtures_dir, 'scenario', 'source.md')

    with open(source_path, 'r', encoding='utf-8') as f:
        input_text = f.read()
    input_lines = input_text.split('\n')

    # Import from local_translate to get exact same logic
    import local_translate as lt
    lt.load_glossary(os.path.join(repo_dir, 'docs', 'en', 'glossary', 'index.md'))

    blocks = lt.split_into_blocks(input_lines)
    responses = {}
    ok = 0
    fail = 0
    total_blocks = 0

    for block_type, indices in blocks:
        if block_type == 'skip':
            continue

        total_blocks += 1
        block_lines = [input_lines[i] for i in indices]
        block_text = '\n'.join(block_lines)

        # Find relevant terms (same as local_translate.translate_block)
        term_keys = lt.find_relevant_terms(block_text)

        # Build user_prompt exactly as local_translate does
        line_rule = ""
        if len(indices) > 1:
            n = len(indices)
            line_rule = (f"The text has exactly {n} lines. Keep exactly {n} lines, "
                         f"preserving line breaks, list markers and indentation.\n\n")

        user_prompt = (f"{lt.build_glossary_hint(term_keys)}{line_rule}"
                       f"Translate from English to Russian:\n===\n{block_text}\n===\nTranslation:")

        # Generate mock response: same structure, Russian text, preserved inline code
        mock_resp = _make_mock(indices, block_lines, block_text, lt._is_table_separator)

        key = hashlib.sha256(user_prompt.encode('utf-8')).hexdigest()
        responses[key] = mock_resp

        actual_lines = len(mock_resp.split('\n')) if mock_resp else 0
        if actual_lines == len(indices):
            ok += 1
        else:
            fail += 1
            print(f"  LINE MISMATCH block L{indices[0]+1}: expected {len(indices)}, got {actual_lines}")

    output_path = os.path.join(fixtures_dir, 'scenario', 'responses.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(responses, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(responses)} mock responses from {total_blocks} blocks")
    print(f"  Verified: {ok} blocks OK, {fail} blocks FAIL")


def _make_mock(indices, block_lines, block_text, is_table_sep_fn):
    """Generate a plausible mock translation response with matching structure.

    Rules:
    - Same number of lines
    - Preserve inline code (`...`) byte-identically
    - Preserve heading prefixes (#, ##, etc.)
    - Preserve list markers (-, *, 1.)
    - Preserve table separator rows
    - Contain Cyrillic text (no EN leakage)
    - Preserve code fences
    """
    out = []

    def preserve_inline(s):
        """Replace non-code parts with [RU] markers, keep inline code `...` intact."""
        parts = s.split('`')
        result = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Inside inline code - preserve exactly
                result.append(part)
            else:
                # Outside inline code - mark as translated
                if part.strip():
                    result.append(part + '[RU]')
                else:
                    result.append(part)
        # Re-insert backticks at the right positions
        return '`'.join(result)

    for line in block_lines:
        s = line.strip()
        if not s:
            out.append('')
            continue
        if s.startswith('```') or s.startswith('~~~'):
            out.append(s)
            continue
        if is_table_sep_fn(line):
            out.append(s)
            continue

        # Check if it's a heading - keep prefix
        hm = __import__('re').match(r'^(#{1,6})\s+(.*)', s)
        if hm:
            hashes, body = hm.group(1), hm.group(2)
            # Preserve inline code in body, translate the rest
            translated_body = preserve_inline(body)
            out.append(f"{hashes} {translated_body}")
            continue

        # Check if it's a list item
        lm = __import__('re').match(r'^(\s*)([-*+]|\d+\.)\s+(.*)', s)
        if lm:
            indent, marker, body = lm.group(1), lm.group(2), lm.group(3)
            translated_body = preserve_inline(body)
            out.append(f"{indent}{marker} {translated_body}")
            continue

        # Regular text: preserve inline code, mark the rest
        out.append(preserve_inline(s))

    return '\n'.join(out)


if __name__ == '__main__':
    main()
