#!/usr/bin/env python3
"""techdoc_translator.py — Generic EN→RU markdown technical translator.

Paragraph-based: consecutive prose lines are translated as one block so the
model keeps context. Only glossary terms actually present in the block are
mentioned in the prompt; Russian equivalents are force-applied afterwards.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from difflib import SequenceMatcher

# Total deadline across all requests: env TOTAL_DEADLINE_SECONDS > 0 → enforce
_TOTAL_DEADLINE_S = int(os.environ.get("TOTAL_DEADLINE_SECONDS", "0"))
_DEADLINE_START = time.monotonic() if _TOTAL_DEADLINE_S > 0 else 0


def _deadline_remaining():
    """Seconds left on the total deadline; returns 0 if exhausted."""
    if _TOTAL_DEADLINE_S <= 0:
        return 0  # feature off
    elapsed = time.monotonic() - _DEADLINE_START
    return max(0, _TOTAL_DEADLINE_S - elapsed)


# E-003 (hint style), E-004 (temperature), E-006 (codeguard): see EXPERIMENTS-003, E-004, E-006
PROMPT_VERSION = "2026.11-r5"  # r5: span-restore handles decoration (added backticks) and dropped backticks
CONTRACT_VERSION = "1.0.0"

SYSTEM_PROMPT = ("You are a translator. Translate only the text between === markers. "
                 "Keep markdown formatting intact: **bold**, `code`, and list markers. "
                 "Never add, remove, or translate backticks or their contents: every "
                 "`code` span must appear character-for-character identical.")
# E-006 variant: TRANSLATE_PROMPT=codeguard adds an explicit code-span guard
SYSTEM_PROMPT_CODEGUARD = SYSTEM_PROMPT + (
    " Never change anything inside backticks: identifiers, enum values and file "
    "paths must appear character-for-character identical.")
OLLAMA_DEFAULT_HOST = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "local-model"
MAX_GLOSSARY_HINTS = 10

BACKEND = os.environ.get("TRANSLATE_BACKEND", "local").lower()

# Generic markdown metadata keys — lines matching these at the top of a file
# are treated as metadata (YAML-style `Key: value` up to the first blank line
# or heading).  This is NOT the source-of-truth list; it is a heuristic for
# deciding which lines to leave untranslated.
_GENERIC_META_KEYS = (
    "id", "title", "Title", "version", "Version", "status", "Status",
    "date", "Date", "author", "Author",
    "source", "Source", "participants", "Participants", "references",
    "Last Modified", "Last-Modified",
)


def _is_table_separator(line):
    """Table delimiter row like |---|:--:| — structural, never translated."""
    s = line.strip()
    return bool(s) and set(s) <= set('|-: ') and '-' in s


def _is_generic_metadata(line):
    """Heuristic: a line that starts with a generic metadata key pattern.
    YAML-style `Key: value` or `key: value` at top of file."""
    s = line.strip()
    # Must look like Key: value (colon-space or colon followed by content)
    m = re.match(r'^[A-Za-z][A-Za-z0-9_.-]*\s*:', s)
    if not m:
        return False
    key = m.group(0).rstrip(':').strip()
    return key.lower() in (k.lower() for k in _GENERIC_META_KEYS)


def needs_skip(line, skip_patterns=None):
    """Return True if this line should NOT be translated."""
    if skip_patterns is None:
        skip_patterns = []
    s = line.strip()
    # Empty lines, horizontal rules, table separators
    if not s or bool(re.match(r'^-{3,}\s*$', s)) or _is_table_separator(line):
        return True
    # Metadata lines (generic heuristic)
    keep_metadata = os.environ.get("TRANSLATE_METADATA") != "1"
    if keep_metadata and _is_generic_metadata(line):
        return True
    # Custom skip patterns from CLI
    for rx in skip_patterns:
        if rx.search(line):
            return True
    return False


# ── Glossary loading ────────────────────────────────────────────────

_GLOSSARY_CACHE = {}
_TOCANONICAL_MAP = {}
_TERM_RES = {}   # key -> compiled regex matching EN term anywhere in source text


def load_glossary(path):
    """Load glossary from a markdown file.

    Supported formats (both accepted):
      - ``**English term** (Russian эквивалент)``
      - ``**English term** — русский перевод``

    The glossary is cached globally: if already loaded, returns the existing
    terms without re-reading the file.
    """
    if _GLOSSARY_CACHE:
        return list(_GLOSSARY_CACHE.keys())
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                ls = raw_line.rstrip()
                m = re.match(r'^\*\*(.+?)\*\*\s*\(([^)]+)\)\s*(.*)', ls)
                if m:
                    en_name = m.group(1).strip()
                    ru_name = m.group(2).strip()
                    defn = m.group(3).strip()
                    key = en_name.lower()
                    _GLOSSARY_CACHE[key] = {'line': ls, 'en': en_name, 'ru': ru_name, 'defn': defn}
                else:
                    nm = re.match(r'^\*\*(.+?)\*\*', ls)
                    if nm:
                        key = nm.group(1).strip().lower()
                        _GLOSSARY_CACHE[key] = {'line': ls, 'en': nm.group(1).strip(), 'ru': None, 'defn': ls[len(nm.group(0)):].strip()}
    except Exception as e:
        log(f"[error] Could not read glossary {path}; fix: ensure valid path and encoding. {e}")
        return []
    for key, info in _GLOSSARY_CACHE.items():
        en = info['en']
        if en:
            _TERM_RES[key] = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(en) + r'(?![A-Za-z0-9_])', re.IGNORECASE)
    return list(_GLOSSARY_CACHE.keys())


def find_relevant_terms(text):
    """Glossary keys whose EN term literally occurs in the given text."""
    found = []
    for key, rx in _TERM_RES.items():
        if rx.search(text):
            found.append(key)
    # longest terms first: better hints, and force-apply order matters
    found.sort(key=lambda k: -len(_GLOSSARY_CACHE[k]['en']))
    return found


def build_variation_map():
    if _TOCANONICAL_MAP:
        return
    for key in _GLOSSARY_CACHE:
        variations = [key, key.replace(' ', '')]
        var_lower = key.lower()
        for ch_a, ch_b in [('х', 'x'), ('с', 'c'), ('т', 'm')]:
            variations.append(var_lower.replace(ch_a, ch_b))
        for v in variations:
            _TOCANONICAL_MAP[v] = key


# ── Post-processing: fix typos ─────────────────────────────────────

_known_typo_replacements = {}


def _init_known_typos():
    if _known_typo_replacements:
        return
    # Known model-specific errors from testing a legacy 7B MT model
    for typo, fixed in [
        ('зьюрения', 'зрения'), ('зьюрого', 'зорого'), ('опьть', 'опять'),
        ('пояздить', 'попасть'), ('поясниться', 'затронуты'),
        ('Специялист', 'Специалист'), ('Специялисте', 'Специалисте'),
        ('Архитхектор', 'Архитектор'), ('Архьтектор', 'Архитектор'),
        ('Оркцестрация', 'Оркестрация'), ('оркстрасия', 'оркестрация'),
        ('Абстьякция', 'Абстракция'), ('АбстраЧции', 'Абстракции'),
        ('абстраКции', 'абстракции'), ('Хранит', 'хранит'),
        ('техническои', 'технического'), ('техниконический', 'технический'),
        ('безопасноcти', 'безопасности'), (' spéciaist', 'специалист'),
        ('Архьетор', 'Архитектор'), ('Оркординация', 'координация'),
        ('Orkestration', 'Оркестрация'), ('LLM Abstraction Layer', 'Абстракция над LLM'),
        ('модели больших языковых моделей)', 'LLM)'),
        ('абстраНации', 'абстракции'), ('АбстраМация', 'Абстракция'),
        ('Специаиист', 'Специалист'), (' conhodenicialnost\'ju', 'конфиденциальностью'),
        ('зьюрить', 'зрить'), ('зюрьба', 'зурьба'),
        ('промпта', 'запроса'), ('опредеят', 'определяет'),
        ('опеделяет', 'определяет'), ('опредета', 'определяет'),
        ('зьюрение', 'зрение'), ('безопьность', 'безопасность'),
        ('абстраНакции', 'абстракции'), ('Оркорстрация', 'Оркестрация'),
        ('Специаилст', 'Специалист'), ('спецаилист', 'специалист'),
        ('стандартов и конфиденциальностей', 'стандартов и конфиденциальностью'),
        ('безопьности', 'безопасности'),
        ('Архитель', 'Архитектор'), ('архитель', 'архитектор'),
        ('экспласации', 'эксплуатации'), ('экспласацию', 'эксплуатацию'),
        ('Архетектор', 'Архитектор'), ('архетектор', 'архитектор'),
        ('Архитесутр', 'Архитектор'), ('архитесутр', 'архитектор'),
        ('Архитетор', 'Архитектор'), ('архитетор', 'архитектор'),
        ('эксплазии', 'эксплуатации'), ('эксплази', 'эксплуатаци'),
        ('анализирает', 'анализирует'), ('анализирает', 'анализирует'),
        ('Оркекстрация', 'Оркестрация'), ('оркекстрация', 'оркестрация'),
        ('анализиреть', 'анализирует'), ('целесостьности', 'целесообразности'),
        ('целесостьность', 'целесообразность'),
    ]:
        _known_typo_replacements[typo] = fixed


def fix_known_terms(text):
    _init_known_typos()

    # Pass 1: known typo replacements
    for typo, correct in sorted(_known_typo_replacements.items(), key=lambda x: -len(x[0])):
        count_before = text.count(typo)
        if count_before > 0:
            text = text.replace(typo, correct)
            log(f"[fix] '{typo}' -> '{correct}' x{count_before}")

    # Pass 2: **bold** terms from glossary
    build_variation_map()
    bold_matches = list(re.finditer(r'\*\*([^*]+?)\*\*', text))
    replacement_spans = []
    for m in bold_matches:
        term_lower = m.group(1).strip().lower()
        found_canonical = _TOCANONICAL_MAP.get(term_lower)
        if not found_canonical:
            for variation, canonical in _TOCANONICAL_MAP.items():
                if variation != term_lower and variation in term_lower and len(term_lower) - len(variation) <= 3:
                    found_canonical = canonical
                    break
        if found_canonical:
            ru = _GLOSSARY_CACHE[found_canonical]['ru']
            if ru:
                replacement_spans.append((m.start(), m.end(), f"**{found_canonical}** ({ru})"))
    if replacement_spans:
        result_chars = list(text)
        for start, end, new_text in sorted(replacement_spans, key=lambda x: x[0], reverse=True):
            result_chars[start:end] = list(new_text)
        text = ''.join(result_chars)

    # Pass 3: fuzz-correct mid-word typos of Russian glossary terms.
    build_variation_map()
    term_index = []
    for info in _GLOSSARY_CACHE.values():
        ru = info['ru']
        if ru and len(ru) >= 6:
            term_index.append(ru.lower())
    if term_index:
        protected = [m.span() for m in re.finditer(r'`[^`]+`', text)]

        def tok_protected(start, end):
            return any(start < pe and end > ps for ps, pe in protected)

        out = []
        last = 0
        for m in re.finditer(r'[А-Яа-яЁё][А-Яа-яЁё-]+', text):
            tok = m.group(0)
            tl = tok.lower()
            if tok_protected(m.start(), m.end()):
                continue
            best = None
            best_ratio = 0.0
            for ru in term_index:
                if tl == ru:
                    best = None
                    break
                if tl[0] != ru[0] or tl[-1] != ru[-1]:
                    continue
                max_len_diff = 3 if len(ru) >= 8 else 2
                if abs(len(tl) - len(ru)) > max_len_diff:
                    continue
                ratio = SequenceMatcher(None, tl, ru).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = ru
            if best and best_ratio >= (0.7 if len(ru) >= 8 else 0.78):
                repl = best
                if tok[0].isupper():
                    repl = repl[0].upper() + repl[1:]
                log(f"[fuzz-fix] '{tok}' -> '{repl}' (ratio {best_ratio:.2f})")
                out.append(text[last:m.start()])
                out.append(repl)
                last = m.end()
        if last:
            out.append(text[last:])
            text = ''.join(out)

    return text


PATH_RX = re.compile(r'[\w\-.]+[.](?:md|yaml|yml|json|py|sh|txt|toml)\b')
LIST_RX = re.compile(r'^(\s*)(?:([-*+])|(\d+\.))\s+')


def restore_heading_prefix(src_line, translated):
    """Headings are translated but the '#' prefix must survive; restore it
    from the source if the model dropped or mangled it."""
    m = re.match(r'^(\s*#{1,6}\s+)', src_line)
    if not m:
        return translated
    want = m.group(1).strip()
    t = translated.strip()
    tm = re.match(r'^(#{1,6})\s+(.*)$', t)
    if tm and tm.group(1) == want:
        return translated
    body = tm.group(2) if tm else t
    return f"{want} {body}"


def restore_list_marker(src_line, translated):
    """Model often drops '1.' / '-' markers; restore from the source line."""
    m = LIST_RX.match(src_line)
    if not m:
        return translated
    want = m.group(2) or m.group(3)
    t = translated.lstrip()
    tm = LIST_RX.match(t)
    if tm and (tm.group(2) or tm.group(3)) == want:
        return translated
    if tm:
        t = LIST_RX.sub('', t, count=1)
    return f"{m.group(1)}{want} {t}"


def restore_paths(translated, src_line):
    """Model mangles paths with Cyrillic homoglyphs; fuzzy-restore."""
    for sp in set(PATH_RX.findall(src_line)):
        if sp in translated:
            continue
        for m in re.finditer(r'[A-Za-zА-Яа-яЁё0-9_\-./]+\.[A-Za-z]{1,5}\b', translated):
            tok = m.group(0)
            if SequenceMatcher(None, tok.lower(), sp.lower()).ratio() >= 0.75:
                log(f"[path-fix] '{tok}' -> '{sp}'")
                translated = translated[:m.start()] + sp + translated[m.end():]
                break
    return translated


_global_gloss_replacements = 0
_global_span_restores = 0


def enforce_glossary(text, term_keys):
    """Hard-substitute Russian equivalents for terms the model left in English.
    Skips spans inside **bold** (handled by fix pass 2) and `inline code`.
    Updates _global_gloss_replacements counter (see summary-json support)."""
    global _global_gloss_replacements
    protected = []
    for rx in (r'\*\*[^*]+\*\*', r'`[^`]+`'):
        for m in re.finditer(rx, text):
            protected.append((m.start(), m.end()))

    def is_protected(start, end):
        return any(start < pe and end > ps for ps, pe in protected)

    block_repl = 0
    for key in term_keys:
        info = _GLOSSARY_CACHE.get(key)
        if not info or not info['ru']:
            continue
        rx = _TERM_RES.get(key)
        if not rx:
            continue
        out = []
        last = 0
        n_repl = 0
        for m in rx.finditer(text):
            if is_protected(m.start(), m.end()):
                continue
            ru = info['ru']
            src = m.group(0)
            if src[0].isupper():
                ru = ru[0].upper() + ru[1:]
            out.append(text[last:m.start()]); out.append(ru)
            last = m.end()
            n_repl += 1
        if n_repl:
            out.append(text[last:])
            text = ''.join(out)
            log(f"[gloss-apply] '{info['en']}' -> '{info['ru']}' x{n_repl}")
            block_repl += n_repl
    _global_gloss_replacements += block_repl
    return text


# ── Translation engine ─────────────────────────────────────────────

HINT_STYLES = {
    "plain": "The following words must be translated as shown:",
    "verbose": "Glossary (use exactly these term translations):",
    "strict": ("Terminology table. Apply a translation ONLY where the exact English "
               "term itself occurs; never use these Russian words for other words:"),
}


def build_glossary_hint(term_keys):
    pairs = []
    for k in term_keys[:MAX_GLOSSARY_HINTS]:
        info = _GLOSSARY_CACHE.get(k)
        if info and info['ru']:
            pairs.append(f"- {info['en']} -> {info['ru']}")
    if not pairs:
        return ""
    header = HINT_STYLES.get(os.environ.get("TRANSLATE_HINT_STYLE", "plain"), HINT_STYLES["plain"])
    return header + "\n" + "\n".join(pairs) + "\n\n"


def _call_cloud(user_prompt, model_name):
    """Cloud backend via OpenAI-compatible API."""
    key = os.environ.get("TRANSLATE_API_KEY")
    base = os.environ.get("TRANSLATE_API_BASE")
    if not key or not base:
        log("[error] cloud backend requires TRANSLATE_API_BASE and TRANSLATE_API_KEY; fix: export these ENV vars or add them to .env")
        return None
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "120"))
    remaining = _deadline_remaining()
    if remaining > 0:
        timeout = min(timeout, int(remaining))
    max_attempts = int(os.environ.get("MAX_RETRIES", "2"))
    temp = float(os.environ.get("TRANSLATE_TEMP", "0.2"))
    top_p = float(os.environ.get("TRANSLATE_TOP_P", "0.95"))
    sys_prompt = SYSTEM_PROMPT_CODEGUARD if os.environ.get("TRANSLATE_PROMPT") == "codeguard" else SYSTEM_PROMPT
    payload = {
        "model": model_name, "temperature": temp, "top_p": top_p, "stream": False,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    extra_kwargs = os.environ.get("TRANSLATE_CHAT_KWARGS")
    if extra_kwargs:
        try:
            payload["chat_template_kwargs"] = json.loads(extra_kwargs)
        except json.JSONDecodeError as e:
            log(f"[error] bad TRANSLATE_CHAT_KWARGS JSON: {e}; fix: provide valid JSON string")
    url = base.rstrip('/') + "/chat/completions"
    for attempt in range(max_attempts):
        if _TOTAL_DEADLINE_S > 0 and _deadline_remaining() <= 0:
            log("[error] total deadline exceeded; fix: increase TOTAL_DEADLINE_SECONDS")
            return None
        tmp_path = None
        try:
            tmp_path = tempfile.mktemp(suffix='.json')
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False); fh.flush()
            curl_timeout = max(5, timeout)
            cmd = ["curl", "-sf", url,
                   "-H", "Content-Type: application/json",
                   "-H", f"Authorization: Bearer {key}",
                   "--data-binary", f"@{tmp_path}"]
            proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=curl_timeout)
            if proc_result.returncode != 0:
                log(f"[retry] cloud attempt {attempt+1}/{max_attempts}"); continue
            resp_data = json.loads(proc_result.stdout)
            choices = resp_data.get("choices", [])
            raw_response = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
            if not raw_response:
                log(f"[empty] cloud attempt {attempt+1}/{max_attempts}"); continue
            return clean_response(raw_response)
        except subprocess.TimeoutExpired:
            log(f"[timeout] cloud attempt {attempt+1}/{max_attempts}")
        except Exception as e:
            log(f"[error] cloud attempt {attempt+1}: {str(e)[:60]}; fix: check API connectivity")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.unlink(tmp_path); tmp_path = None
                except FileNotFoundError: pass
    return None


# ── Mock backend (for tests) ────────────────────────────────────────

def _load_mock_responses(mock_dir):
    """Load responses.json from mock_dir. Returns dict {sha256hex(text): response}."""
    global _MOCK_RESPONSES
    if _MOCK_RESPONSES is not None and "loaded" in _MOCK_RESPONSES:
        return _MOCK_RESPONSES
    path = os.path.join(mock_dir, "responses.json")
    if not os.path.isfile(path):
        _MOCK_RESPONSES = {}
        return _MOCK_RESPONSES
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _MOCK_RESPONSES = {"loaded": True}
        for k, v in data.items():
            _MOCK_RESPONSES[k] = v
        log(f"[mock] loaded {len(data)} responses from {path}")
    except Exception as e:
        log(f"[error] could not load mock responses {path}; fix: check file path and JSON validity. {e}")
        _MOCK_RESPONSES = {}
    return _MOCK_RESPONSES


def _call_mock(user_prompt, model_name):
    """Mock backend: look up sha256(text) in responses.json."""
    mock_dir = os.environ.get("TRANSLATE_MOCK_DIR", "")
    if not mock_dir:
        log("[error] TRANSLATE_MOCK_DIR not set; fix: export path to mock directory")
        return None
    _load_mock_responses(mock_dir)
    key = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()
    resp = _MOCK_RESPONSES.get(key)
    if resp is None:
        log(f"[mock] miss for prompt sha256={key[:16]}...")
        return None
    log(f"[mock] hit for prompt sha256={key[:16]}...")
    return clean_response(resp)


_MOCK_RESPONSES = None

def call_model(user_prompt, model_name):
    """Dispatch to the configured backend. Returns cleaned text or None."""
    if BACKEND == "cloud":
        return _call_cloud(user_prompt, model_name)
    if BACKEND == "mock":
        return _call_mock(user_prompt, model_name)
    host = os.environ.get("TRANSLATE_API_BASE", OLLAMA_DEFAULT_HOST)
    if host.rstrip('/').endswith('/v1'):
        return _call_local_openai(user_prompt, host, model_name)
    return _call_local(user_prompt, host, model_name)


def _call_local_openai(user_prompt, host_url, model_name):
    """Local backend for OpenAI-compatible servers (base URL ends with /v1).

    Same wire format as the cloud backend but no key is required: local
    servers (llama.cpp, vLLM, etc.) usually accept unauthenticated requests."""
    base = host_url.rstrip('/')
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "120"))
    if _TOTAL_DEADLINE_S > 0:
        remaining = _deadline_remaining()
        if remaining > 0:
            timeout = min(timeout, int(remaining))
    max_attempts = int(os.environ.get("MAX_RETRIES", "2"))
    temp = float(os.environ.get("TRANSLATE_TEMP", "0.2"))
    top_p = float(os.environ.get("TRANSLATE_TOP_P", "0.95"))
    sys_prompt = SYSTEM_PROMPT_CODEGUARD if os.environ.get("TRANSLATE_PROMPT") == "codeguard" else SYSTEM_PROMPT
    payload = {
        "model": model_name, "temperature": temp, "top_p": top_p, "stream": False,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    extra_kwargs = os.environ.get("TRANSLATE_CHAT_KWARGS")
    if extra_kwargs:
        try:
            payload["chat_template_kwargs"] = json.loads(extra_kwargs)
        except json.JSONDecodeError as e:
            log(f"[error] bad TRANSLATE_CHAT_KWARGS JSON: {e}; fix: provide valid JSON string")
    url = base + "/chat/completions"
    for attempt in range(max_attempts):
        if _TOTAL_DEADLINE_S > 0 and _deadline_remaining() <= 0:
            log("[error] total deadline exceeded")
            return None
        tmp_path = None
        try:
            tmp_path = tempfile.mktemp(suffix='.json')
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False); fh.flush()
            cmd = ["curl", "-sf", url, "-H", "Content-Type: application/json"]
            key = os.environ.get("TRANSLATE_API_KEY")
            if key:
                cmd += ["-H", f"Authorization: Bearer {key}"]
            cmd += ["--data-binary", f"@{tmp_path}"]
            curl_timeout = max(5, timeout)
            proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=curl_timeout)
            if proc_result.returncode != 0:
                log(f"[retry] local-openai attempt {attempt+1}/{max_attempts}"); continue
            resp_data = json.loads(proc_result.stdout)
            choices = resp_data.get("choices", [])
            raw_response = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
            if not raw_response:
                log(f"[empty] local-openai attempt {attempt+1}/{max_attempts}"); continue
            return clean_response(raw_response)
        except subprocess.TimeoutExpired:
            log(f"[timeout] local-openai attempt {attempt+1}/{max_attempts}")
        except Exception as e:
            log(f"[error] local-openai attempt {attempt+1}: {str(e)[:60]}; fix: check local server at {url}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.unlink(tmp_path); tmp_path = None
                except FileNotFoundError: pass
    return None


def _call_local(user_prompt, host_url, model_name):
    """Local backend (Ollama-compatible API)."""
    payload = {
        "model": model_name, "prompt": user_prompt, "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": float(os.environ.get("TRANSLATE_TEMP", "0.2")),
            "top_p": float(os.environ.get("TRANSLATE_TOP_P", "0.95")),
        }
    }
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "120"))
    if _TOTAL_DEADLINE_S > 0:
        remaining = _deadline_remaining()
        if remaining > 0:
            timeout = min(timeout, int(remaining))
    max_attempts = int(os.environ.get("MAX_RETRIES", "2"))

    for attempt in range(max_attempts):
        if _TOTAL_DEADLINE_S > 0 and _deadline_remaining() <= 0:
            log("[error] total deadline exceeded")
            return None
        tmp_path = None
        try:
            tmp_path = tempfile.mktemp(suffix='.json')
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False); fh.flush()
            cmd = ["curl", "-sf", f"{host_url}/api/generate",
                   "-H", "Content-Type: application/json", "--data-binary", f"@{tmp_path}"]
            curl_timeout = max(5, timeout)
            proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=curl_timeout)
            if proc_result.returncode != 0:
                log(f"[retry] attempt {attempt+1}/{max_attempts}"); continue
            resp_data = json.loads(proc_result.stdout)
            raw_response = resp_data.get("response", "").strip()
            if not raw_response:
                log(f"[empty] attempt {attempt+1}/{max_attempts}"); continue
            return clean_response(raw_response)
        except subprocess.TimeoutExpired:
            log(f"[timeout] attempt {attempt+1}/{max_attempts}")
        except Exception as e:
            log(f"[error] attempt {attempt+1}: {str(e)[:60]}; fix: check local server at {host_url}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.unlink(tmp_path); tmp_path = None
                except FileNotFoundError: pass
    return None


def translate_block(block_text, term_keys, model_name):
    """Translate a multi-line paragraph. Returns list of lines or None."""
    n_lines = block_text.count('\n') + 1
    line_rule = ""
    if n_lines > 1:
        line_rule = (f"The text has exactly {n_lines} lines. Keep exactly {n_lines} lines, "
                     f"preserving line breaks, list markers and indentation.\n\n")
    user_prompt = (f"{build_glossary_hint(term_keys)}{line_rule}"
                   f"Translate from English to Russian:\n===\n{block_text}\n===\nTranslation:")
    translated = call_model(user_prompt, model_name)
    if not translated:
        return None
    out_lines = translated.split('\n')
    if len(out_lines) != n_lines:
        log(f"[linecount] expected {n_lines}, got {len(out_lines)} -> line-by-line fallback")
        return None
    return [l for l in out_lines]


def restore_code_spans(translated, src_line):
    """Invariant: inline-code spans are identifiers — the model must not
    translate, add, or drop them. Equal span counts: positional restore from
    source. Count mismatch: multiset adjustment."""
    rx = re.compile(r'`([^`]+)`')
    src_spans = rx.findall(src_line)
    global _global_span_restores
    if not rx.search(translated) and not src_spans:
        return translated
    n = 0

    def counted(val):
        nonlocal n
        n += 1
        log(f"[span-restore] decorated/translated span -> `{val[:20]}`")
        return val

    # pass 1 — equal counts: positional restore
    if len(rx.findall(translated)) == len(src_spans):
        it = iter(src_spans)
        def repl(m):
            nonlocal n
            ru = m.group(1); en = next(it)
            if ru != en:
                n += 1
                log(f"[span-restore] `{'' if len(ru)>20 else ru}` -> `{en}`")
            return f"`{en}`"
        out = rx.sub(repl, translated)
        _global_span_restores += n
        return out

    # multiset adjustment for count mismatches
    from collections import Counter
    need = Counter(src_spans)
    src_bare = re.sub(r'`[^`]+`', ' ', src_line)
    cyrillic = re.compile(r'[\u0400-\u04FF\u0500-\u052F]')

    def decide(m):
        val = m.group(1)
        if need[val] > 0:
            need[val] -= 1
            return f'`{val}`'
        if re.search(r'(?<![\w`/])' + re.escape(val) + r'(?![\w`/])',
                     src_bare, re.IGNORECASE):
            return counted(val)
        if cyrillic.search(val):
            for cand in list(need):
                if need[cand] > 0 and not cyrillic.search(cand):
                    need[cand] -= 1
                    counted(cand)
                    return f'`{cand}`'
        return m.group(0)

    out = rx.sub(decide, translated)

    for val, k in list(need.items()):
        for _ in range(k):
            wrapped, cnt = re.subn(r'(?<![\w`/])' + re.escape(val) + r'(?![\w`/])',
                                   f'`{val}`', out, count=1)
            if not cnt:
                for info in _GLOSSARY_CACHE.values():
                    ru_eq = info.get('ru') or ''
                    if (info['en'].lower() == val.lower() and ru_eq
                            and not cyrillic.search(val)):
                        wrapped, cnt = re.subn(
                            r'(?<![\w`/])' + re.escape(ru_eq) + r'(?![\w`/])',
                            f'`{val}`', out, count=1)
                        if cnt:
                            break
            if cnt:
                out = wrapped
                counted(val)
            else:
                break
    _global_span_restores += n
    return out


LITERAL_TOKENS = {
    'allow', 'deny', 'yes', 'no', 'true', 'false', 'null', 'none',
    'optional', 'required', 'mandatory', 'read', 'write', 'only', 'reason',
    'frontmatter', 'draft', 'active', 'deprecated',
}


def _is_translatable_content(line):
    """True if the line contains ordinary Latin words that translation must
    change; identifiers, inline code, URLs, paths and LITERAL_TOKENS do not count."""
    s = re.sub(r'`[^`]+`', ' ', line)
    s = re.sub(r'https?://\S+', ' ', s)
    s = re.sub(r'\S*/\S+\.\S+', ' ', s)
    for w in re.findall(r'[A-Za-z][A-Za-z0-9]*', s):
        if '_' in w or re.search(r'[a-z][A-Z]', w) or w.isupper():
            continue
        if w.lower() in LITERAL_TOKENS:
            continue
        if len(w) >= 3:
            return True
    return False


def translate_line_fallback(line_text, term_keys, model_name):
    cl = line_text.strip()
    if not cl:
        return ""
    user_prompt = (f"{build_glossary_hint(term_keys)}"
                   f"Translate from English to Russian:\n===\n{cl}\n===\nTranslation:")
    t = call_model(user_prompt, model_name)
    if t is None:
        return None
    collapsed = re.sub(r'\s*\n\s*', ' ', t).strip()
    return collapsed if collapsed else None


def clean_response(raw):
    if not raw:
        return ""
    for marker in ['</|', '\uFEFF', '\ufffd']:
        idx = raw.find(marker)
        if 0 < idx < len(raw) * 0.8:
            raw = raw[:idx].strip(); break
    cleaned_chars = []
    for ch in raw:
        code = ord(ch)
        if (code >= 0x20) or (ch in '\n\r\t') or (0xC0 <= code <= 0x04FF):
            cleaned_chars.append(ch)
        else:
            cleaned_chars.append(' ')
    cleaned = ''.join(cleaned_chars)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned).strip()
    cleaned = re.sub(r'<br\s*/?>', ' ', cleaned)
    cleaned = re.sub(r'^\s*={2,}\s*$', '', cleaned, flags=re.MULTILINE).strip()
    cleaned = re.sub(r'\s*={3,}\s*', ' ', cleaned).strip()
    cleaned = re.sub(r'^(\*\*)?\s*Translation\s*:?\s*(\*\*)?\s*', '', cleaned)
    for pat in [r'\bYou are a\b', r'\bTranslate.*English\b']:
        m = re.search(pat, cleaned, re.IGNORECASE)
        if m and m.start() < len(cleaned) * 0.6:
            cleaned = cleaned[:m.start()].rstrip('.!?').strip(); break
    return cleaned


# ── Block splitting ─────────────────────────────────────────────────

def split_into_blocks(input_lines, skip_patterns=None):
    """Group consecutive translatable lines into paragraph blocks."""
    if skip_patterns is None:
        skip_patterns = []
    blocks = []
    force_section = os.environ.get("TRANSLATE_FORCE_SECTION") == "1"
    fence_active = False
    current = []

    def flush():
        nonlocal current
        while current and not input_lines[current[-1]].strip():
            current.pop()
        while current and not input_lines[current[0]].strip():
            current.pop(0)
        if current:
            blocks.append(('para', current))
            current = []

    for idx, line in enumerate(input_lines):
        if re.match(r'^\s*```', line):
            flush()
            blocks.append(('skip', [idx]))
            fence_active = not fence_active
            continue
        if force_section and not fence_active and not line.strip():
            current.append(idx)
            continue
        if fence_active or needs_skip(line, skip_patterns):
            flush()
            blocks.append(('skip', [idx]))
        else:
            current.append(idx)
    flush()
    return blocks


# ── Main ────────────────────────────────────────────────────────────

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def sha256_of_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_report(report_path, report_data):
    """Write a JSON report; exit 6 on failure."""
    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report_data, fh, ensure_ascii=False, indent=2, default=str)
            fh.write("\n")
    except Exception as e:
        log(f"[error] failed to write report {report_path}; fix: check path and permissions. {e}")
        sys.exit(6)


def write_report_from_args(args, stats, backend, model, exit_code, message):
    report_data = {
        "ok": stats["ok"],
        "skip": stats["skip"],
        "fail": stats["fail"],
        "backend": backend,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "glossary_applied": _global_gloss_replacements,
        "source_sha256": args.source_sha,
        "output_sha256": args.output_sha,
        "exit_code": exit_code,
        "contract_version": CONTRACT_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()),
        "message": message,
    }
    if args.report:
        write_report(args.report, report_data)
    if args.summary_json:
        print(json.dumps(report_data), file=sys.stderr, flush=True)
    return report_data


def main():
    # ── Minimal arg parsing (no argparse dependency needed) ──
    args = type('Args', (), {})()
    args.input_en = None
    args.output_ru = None
    args.glossary = None
    args.report = None
    args.allow_cloud = False
    args.skip_patterns = []
    args.version = False
    args.summary_json = False
    args.contract_version = None

    i = 0
    argv = sys.argv[1:]
    while i < len(argv):
        a = argv[i]
        if a == '--input-en':
            i += 1; args.input_en = argv[i]
        elif a == '--output-ru':
            i += 1; args.output_ru = argv[i]
        elif a == '--glossary':
            i += 1; args.glossary = argv[i]
        elif a == '--report':
            i += 1; args.report = argv[i]
        elif a == '--allow-cloud':
            args.allow_cloud = True
        elif a == '--skip-pattern':
            i += 1
            try:
                args.skip_patterns.append(re.compile(argv[i]))
            except re.error as e:
                log(f"[error] invalid regex in --skip-pattern '{argv[i]}'; fix: provide valid regex. {e}")
                sys.exit(1)
        elif a == '--version':
            args.version = True
        elif a == '--summary-json':
            args.summary_json = True
        elif a == '--contract-version':
            i += 1; args.contract_version = argv[i]
        elif a == '--help' or a == '-h':
            _print_help()
            sys.exit(0)
        else:
            log(f"[error] unknown option '{a}'; fix: use --help for usage info")
            sys.exit(1)
        i += 1

    if args.version:
        print(f"techdoc-translator {CONTRACT_VERSION} (prompt {PROMPT_VERSION})", file=sys.stderr)
        print(f"PROMPT_VERSION={PROMPT_VERSION}", file=sys.stderr)
        sys.exit(0)

    # Contract version check
    if args.contract_version is not None:
        if args.contract_version != CONTRACT_VERSION:
            msg = f"contract version mismatch: requested {args.contract_version}, got {CONTRACT_VERSION}"
            log(f"[error] {msg}; fix: use the version this binary was built for")
            sys.exit(5)

    # Validate required args
    if not args.input_en:
        log("[error] --input-en is required; fix: provide source markdown file path")
        sys.exit(1)

    if not args.output_ru:
        log("[error] --output-ru is required; fix: provide output markdown file path")
        sys.exit(1)

    if not os.path.exists(args.input_en):
        log(f"[error] source file not found: {args.input_en}; fix: check file path")
        sys.exit(1)

    # Cloud backend checks
    if BACKEND == "cloud":
        if not args.allow_cloud:
            log("[error] cloud backend selected but --allow-cloud not passed; fix: either set TRANSLATE_BACKEND=local or pass --allow-cloud to enable cloud mode")
            sys.exit(2)
        api_key = os.environ.get("TRANSLATE_API_KEY")
        api_base = os.environ.get("TRANSLATE_API_BASE")
        if not api_key or not api_base:
            log("[error] cloud backend requires TRANSLATE_API_BASE and TRANSLATE_API_KEY; fix: export these ENV vars or add to .env")
            sys.exit(2)
        model = os.environ.get("TRANSLATE_MODEL", "")
    else:
        model = os.environ.get("TRANSLATE_MODEL", OLLAMA_DEFAULT_MODEL)

    # Load glossary
    load_glossary(args.glossary)
    log(f"[debug] Glossary loaded: {len(_GLOSSARY_CACHE)} terms")

    # Reset global counters
    global _global_gloss_replacements
    _global_gloss_replacements = 0
    global _global_span_restores
    _global_span_restores = 0

    # Read source
    try:
        with open(args.input_en, "r", encoding="utf-8") as fh:
            source_text = fh.read()
    except Exception as e:
        log(f"[error] could not read source file; fix: check permissions. {e}")
        sys.exit(1)

    args.source_sha = sha256_of_bytes(source_text.encode('utf-8'))

    # Process
    input_lines = source_text.split('\n')
    output_lines = [None] * len(input_lines)
    stats_ok = 0
    stats_skip = 0
    stats_fail = 0
    exit_reason = "ok"

    blocks = split_into_blocks(input_lines, args.skip_patterns)

    for kind, indices in blocks:
        if kind == 'skip':
            for i in indices:
                output_lines[i] = input_lines[i]
            stats_skip += len(indices)
            continue

        block_text = '\n'.join(input_lines[i] for i in indices)
        term_keys = find_relevant_terms(block_text)
        preview = block_text[:60].replace('\n', '\\n')
        log(f"[debug] Block L{indices[0]+1}-{indices[-1]+1}: {repr(preview)} -> {len(term_keys)} terms")

        translated = translate_block(block_text, term_keys, model)
        if translated is None:
            translated = []
            for i in indices:
                t = translate_line_fallback(input_lines[i], term_keys, model)
                translated.append(t if t else input_lines[i])

        for pos, i in enumerate(indices):
            line_out = translated[pos]
            if line_out and line_out.strip() != input_lines[i].strip():
                line_out = restore_list_marker(input_lines[i], line_out)
                line_out = restore_heading_prefix(input_lines[i], line_out)
                line_out = restore_paths(line_out, input_lines[i])
                line_out = fix_known_terms(line_out)
                line_out = enforce_glossary(line_out, term_keys)
                line_out = restore_code_spans(line_out, input_lines[i])
                output_lines[i] = line_out
                stats_ok += 1
            else:
                output_lines[i] = input_lines[i]
                if _is_translatable_content(input_lines[i]):
                    stats_fail += 1
                    log(f"[FAIL] L{i+1} — fallback")
                else:
                    stats_skip += 1

    log(f"\nDone: {stats_ok} ok, {stats_skip} skip, {stats_fail} fail")
    final_output = '\n'.join(l if l is not None else '' for l in output_lines)

    # Write output
    try:
        out_dir = os.path.dirname(args.output_ru)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output_ru, "w", encoding="utf-8") as fh:
            fh.write(final_output)
    except Exception as e:
        log(f"[error] could not write output file; fix: check path and permissions. {e}")
        sys.exit(1)

    args.output_sha = sha256_of_bytes(final_output.encode('utf-8'))

    # Determine exit code
    if stats_fail > 0:
        exit_reason = f"{stats_fail} lines failed translation"
        log(f"[exit] {stats_fail} lines failed translation")
        write_report_from_args(args, {"ok": stats_ok, "skip": stats_skip, "fail": stats_fail},
                               BACKEND, model, 4, exit_reason)
        sys.exit(4)

    write_report_from_args(args, {"ok": stats_ok, "skip": stats_skip, "fail": 0},
                           BACKEND, model, 0, "ok")
    sys.exit(0)


def _print_help():
    print("""Usage: techdoc_translator.py [OPTIONS]

Generic EN→RU markdown technical translator.

Required:
  --input-en PATH       Source English markdown file
  --output-ru PATH      Output Russian markdown file

Optional:
  --glossary PATH       Glossary file (markdown format: **English** (Russian))
  --report PATH         Write JSON run report to file
  --allow-cloud         Enable cloud backend mode
  --skip-pattern REGEX  Skip lines matching regex (repeatable)
  --summary-json        Also print JSON summary to stderr
  --version             Print version info and exit
  --contract-version N  Check contract version (exit 5 if mismatch)
  --help, -h            Show this help

Environment:
  TRANSLATE_BACKEND     local (default) | cloud
  TRANSLATE_API_BASE    Cloud API base URL (cloud mode)
  TRANSLATE_API_KEY     Cloud API key (cloud mode)
  TRANSLATE_MODEL       Model name
  TRANSLATE_TEMP        Temperature (default 0.2)
  TRANSLATE_TOP_P       top_p (default 0.95)
  TRANSLATE_HINT_STYLE  plain | verbose | strict
  TRANSLATE_PROMPT      codeguard (default: none)
  TRANSLATE_CHAT_KWARGS Extra JSON kwargs for chat request
  TRANSLATE_METADATA    "1" to translate metadata lines
  TRANSLATE_FORCE_SECTION "1" to merge all prose into one block
  TRANSLATE_RUN_LOG     File path for JSON run-log
  REQUEST_TIMEOUT       Curl timeout in seconds (default 120)
  MAX_RETRIES           Retries per chunk (default 2)
  TOTAL_DEADLINE_SECONDS Global deadline for all requests (default 0 = off)
  TRANSLATE_MOCK_DIR    Path to mock responses (for testing)

Exit codes:
  0 — success
  1 — invalid input / glossary / parse
  2 — usage error / missing config / cloud not allowed
  3 — backend unavailable (check server is running)
  4 — incomplete translation (some lines failed)
  5 — contract version mismatch
  6 — report write error
""", file=sys.stderr)


if __name__ == "__main__":
    main()
