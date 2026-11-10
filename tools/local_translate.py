#!/usr/bin/env python3
"""local_translate.py — Translate EN→RU via Ollama (kaelri/hy-mt2:7b).

Paragraph-based: consecutive prose lines are translated as one block so the
model keeps context. Only glossary terms actually present in the block are
mentioned in the prompt; Russian equivalents are force-applied afterwards.
"""

import json, os, re, subprocess, sys, tempfile
from difflib import SequenceMatcher


SYSTEM_PROMPT = ("You are a translator. Translate only the text between === markers. "
                 "Keep markdown formatting intact: **bold**, `code`, and list markers.")
# E-006 variant: TRANSLATE_PROMPT=codeguard adds an explicit code-span guard
SYSTEM_PROMPT_CODEGUARD = SYSTEM_PROMPT + (
    " Never change anything inside backticks: identifiers, enum values and file "
    "paths must appear character-for-character identical.")
OLLAMA_DEFAULT_HOST = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "kaelri/hy-mt2:7b"
CLOUD_DEFAULT_BASE = "https://api.neuraldeep.ru/v1"
CLOUD_DEFAULT_MODEL = "qwen3.6-35b-a3b-noreason"
MAX_GLOSSARY_HINTS = 10

BACKEND = os.environ.get("TRANSLATE_BACKEND", "ollama").lower()


def log(msg):
    print(msg, file=sys.stderr, flush=True)


METADATA_KEYS = ('Version:', 'Status:', 'Last Modified:', 'Abstraction:',
                 'changelog-path:', 'Source:', 'ID:', 'Date:', 'Participants:')


def is_metadata_line(line):
    """Document metadata header line (YAML-style keys used by project docs)."""
    s = line.strip()
    return s.startswith(METADATA_KEYS)


def needs_skip(line):
    # Metadata headers stay untranslated by default: existing docs/ru/*/index-RU.md
    # keep English keys/values (machine-parsed by Documenter). E-005 decision.
    # TRANSLATE_METADATA=1 opts back into model translation of those lines.
    s = line.strip()
    keep_metadata = os.environ.get("TRANSLATE_METADATA") != "1"
    return not s or s.startswith('#') or bool(re.match(r'^-{3,}\s*$', s)) or \
        (keep_metadata and is_metadata_line(line))


# ── Glossary loading ────────────────────────────────────────────────

_GLOSSARY_CACHE = {}
_TOCANONICAL_MAP = {}
_TERM_RES = {}   # key -> compiled regex matching EN term anywhere in source text


def load_glossary(path):
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
        log(f"[WARN] Could not read glossary: {e}")
    for key, info in _GLOSSARY_CACHE.items():
        en = info['en']
        if en:
            _TERM_RES[key] = re.compile(r'(?<![A-Za-z0-9])' + re.escape(en) + r'(?![A-Za-z0-9])', re.IGNORECASE)
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
    # Known model-specific errors from testing kaelri/hy-mt2:7b
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
    # Only touches tokens whose first AND last letters match the glossary term,
    # so legitimate inflected endings (which differ at the tail) stay intact.
    build_variation_map()
    term_index = []
    for info in _GLOSSARY_CACHE.values():
        ru = info['ru']
        if ru and len(ru) >= 6:
            term_index.append(ru.lower())
    if term_index:
        # only inline code is truly protected; bold terms are fuzz-corrected too
        # (bold glossary terms with typos, e.g. **Архитетор**, must be fixed)
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
                # first+last letters must match: protects legitimate inflected forms
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
    """Model mangles paths with Cyrillic homoglyphs (project-conьcept); fuzzy-restore."""
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


def enforce_glossary(text, term_keys):
    """Hard-substitute Russian equivalents for terms the model left in English.
    Skips spans inside **bold** (handled by fix pass 2) and `inline code`."""
    protected = []
    for rx in (r'\*\*[^*]+\*\*', r'`[^`]+`'):
        for m in re.finditer(rx, text):
            protected.append((m.start(), m.end()))

    def is_protected(start, end):
        return any(start < pe and end > ps for ps, pe in protected)

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
    return text


# ── Translation engine ─────────────────────────────────────────────

HINT_STYLES = {
    # winner of E-003 (2026-11-10): plain positive wording, 0/3 contamination
    "plain": "The following words must be translated as shown:",
    # former default; verbose wording (E-003: 1/3 contamination)
    "verbose": "Glossary (use exactly these term translations):",
    # negative directive; E-003: 3/3 contamination — DO NOT USE
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


def _cloud_credentials():
    """API key + base URL for the cloud backend. Env overrides config file."""
    key = os.environ.get("NEURALDEEP_API_KEY")
    base = os.environ.get("NEURALDEEP_BASE_URL", CLOUD_DEFAULT_BASE)
    if not key:
        cfg = os.path.expanduser("~/.config/opencode/opencode.json")
        try:
            with open(cfg, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            opts = data.get("provider", {}).get("neuraldeep", {}).get("options", {})
            key = opts.get("apiKey")
            base = os.environ.get("NEURALDEEP_BASE_URL", opts.get("baseURL", base))
        except Exception as e:
            log(f"[WARN] cloud key not found: {e}")
    return key, base


def call_model(user_prompt, model_name):
    """Dispatch to the configured backend. Returns cleaned text or None."""
    if BACKEND == "cloud":
        return _call_cloud(user_prompt, model_name)
    host = os.environ.get("OLLAMA_HOST", OLLAMA_DEFAULT_HOST)
    return _call_ollama(user_prompt, host, model_name)


def _call_cloud(user_prompt, model_name):
    key, base = _cloud_credentials()
    if not key:
        log("[error] no cloud API key"); return None
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "120"))
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
    # optional passthrough for vLLM-style servers, e.g. CLOUD_CHAT_KWARGS='{"enable_thinking":false}'
    extra_kwargs = os.environ.get("CLOUD_CHAT_KWARGS")
    if extra_kwargs:
        try:
            payload["chat_template_kwargs"] = json.loads(extra_kwargs)
        except json.JSONDecodeError as e:
            log(f"[WARN] bad CLOUD_CHAT_KWARGS: {e}")
    url = base.rstrip('/') + "/chat/completions"
    for attempt in range(max_attempts):
        tmp_path = None
        try:
            tmp_path = tempfile.mktemp(suffix='.json')
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False); fh.flush()
            cmd = ["curl", "-sf", url,
                   "-H", "Content-Type: application/json",
                   "-H", f"Authorization: Bearer {key}",
                   "--data-binary", f"@{tmp_path}"]
            proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
            log(f"[error] cloud attempt {attempt+1}: {str(e)[:60]}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.unlink(tmp_path); tmp_path = None
                except FileNotFoundError: pass
    return None


def _call_ollama(user_prompt, host_url, model_name):
    payload = {
        "model": model_name, "prompt": user_prompt, "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": float(os.environ.get("TRANSLATE_TEMP", "0.2")),
            "top_p": float(os.environ.get("TRANSLATE_TOP_P", "0.95")),
        }
    }
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "120"))
    max_attempts = int(os.environ.get("MAX_RETRIES", "2"))

    for attempt in range(max_attempts):
        tmp_path = None
        try:
            tmp_path = tempfile.mktemp(suffix='.json')
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False); fh.flush()
            cmd = ["curl", "-sf", f"{host_url}/api/generate",
                   "-H", "Content-Type: application/json", "--data-binary", f"@{tmp_path}"]
            proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
            log(f"[error] attempt {attempt+1}: {str(e)[:60]}")
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


def translate_line_fallback(line_text, term_keys, model_name):
    cl = line_text.strip()
    if not cl:
        return ""
    user_prompt = (f"{build_glossary_hint(term_keys)}"
                   f"Translate from English to Russian:\n===\n{cl}\n===\nTranslation:")
    return call_model(user_prompt, model_name)


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
    # strip echoed === delimiters the model sometimes reproduces
    cleaned = re.sub(r'^\s*={2,}\s*$', '', cleaned, flags=re.MULTILINE).strip()
    cleaned = re.sub(r'\s*={3,}\s*', ' ', cleaned).strip()
    # strip echoed label prefixes like "**Translation:**" / "Translation:"
    cleaned = re.sub(r'^(\*\*)?\s*Translation\s*:?\s*(\*\*)?\s*', '', cleaned)
    for pat in [r'\bYou are a\b', r'\bTranslate.*English\b']:
        m = re.search(pat, cleaned, re.IGNORECASE)
        if m and m.start() < len(cleaned) * 0.6:
            cleaned = cleaned[:m.start()].rstrip('.!?').strip(); break
    return cleaned


# ── Block splitting ─────────────────────────────────────────────────

def split_into_blocks(input_lines):
    """Group consecutive translatable lines into paragraph blocks.
    Structural lines (headings, rules, blanks, code fences) pass through.
    TRANSLATE_FORCE_SECTION=1: merge all prose into one block (E-007 experiment)."""
    blocks = []          # (kind, indices): 'skip' single index, 'para' list of indices
    force_section = os.environ.get("TRANSLATE_FORCE_SECTION") == "1"
    fence_active = False
    current = []

    def flush():
        nonlocal current
        while current and not input_lines[current[-1]].strip():
            current.pop()  # trailing blanks would break line-count parity
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
            current.append(idx)  # keep blank lines inside the section block
            continue
        if fence_active or needs_skip(line):
            flush()
            blocks.append(('skip', [idx]))
        else:
            current.append(idx)
    flush()
    return blocks


# ── Main ────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        log("Usage: local_translate.py <src_lang> <tgt_lang> [glossary_path]"); sys.exit(1)
    source_lang = sys.argv[1]; target_lang = sys.argv[2]
    glossary_file = sys.argv[3] if len(sys.argv) > 3 else None

    input_text = sys.stdin.read()
    if not input_text.strip(): log("Error: no input"); sys.exit(1)

    if BACKEND == "cloud":
        model = os.environ.get("CLOUD_MODEL", CLOUD_DEFAULT_MODEL)
        log(f"[debug] backend=cloud model={model}")
    else:
        host = os.environ.get("OLLAMA_HOST", OLLAMA_DEFAULT_HOST)
        model = os.environ.get("OLLAMA_MODEL", OLLAMA_DEFAULT_MODEL)
        log(f"[debug] backend=ollama host={host} model={model}")

    all_terms = load_glossary(glossary_file)
    log(f"[debug] Glossary loaded: {len(all_terms)} terms")

    input_lines = input_text.split('\n')
    output_lines = [None] * len(input_lines)
    stats_ok = 0; stats_skip = 0; stats_fail = 0

    for kind, indices in split_into_blocks(input_lines):
        if kind == 'skip':
            for i in indices:
                output_lines[i] = input_lines[i]
            stats_skip += len(indices)
            continue

        block_text = '\n'.join(input_lines[i] for i in indices)
        term_keys = find_relevant_terms(block_text)
        preview = block_text[:60].replace('\n', '\\n')
        log(f"[debug] Block L{indices[0]+1}-{indices[-1]+1}: {repr(preview)} -> "
            f"{len(term_keys)} terms: {[ _GLOSSARY_CACHE[k]['en'] for k in term_keys[:5]]}")

        translated = translate_block(block_text, term_keys, model)
        if translated is None:
            # line-by-line fallback for this block
            translated = []
            for i in indices:
                t = translate_line_fallback(input_lines[i], term_keys, model)
                translated.append(t if t else input_lines[i])

        for pos, i in enumerate(indices):
            line_out = translated[pos]
            if line_out and line_out.strip() != input_lines[i].strip():
                line_out = restore_list_marker(input_lines[i], line_out)
                line_out = restore_paths(line_out, input_lines[i])
                line_out = fix_known_terms(line_out)
                line_out = enforce_glossary(line_out, term_keys)
                output_lines[i] = line_out
                stats_ok += 1
            else:
                output_lines[i] = input_lines[i]
                stats_fail += 1
                log(f"[FAIL] L{i+1} — fallback")

    log(f"\nDone: {stats_ok} ok, {stats_skip} skip, {stats_fail} fail")
    final_output = '\n'.join(l if l is not None else '' for l in output_lines)
    if final_output: print(final_output, end="", flush=True)


if __name__ == "__main__":
    main()
