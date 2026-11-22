#!/usr/bin/env bash
# collect_telemetry.sh -- Local opt-in diagnostics collector.
#
# Usage:
#   collect_telemetry.sh                     # collect from stdin (JSONL)
#   collect_telemetry.sh --collect           # same
#   collect_telemetry.sh --inspect           # print summary only
#   collect_telemetry.sh --bundle            # write gzip-tar bundle to stdout
#   collect_telemetry.sh --read <file>       # inspect a bundle file
#   collect_telemetry.sh --help              # show help

_PYTHON_TMP=$(mktemp --suffix=.py)
trap "rm -f \"$_PYTHON_TMP\"" EXIT

cat > "$_PYTHON_TMP" <<'PY'
import sys, os, json, re, tarfile, hashlib, datetime, tempfile, glob

# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------
def parse_config():
    cfg = {}
    p = os.path.join(".council", "telemetry.yml")
    if not os.path.isfile(p):
        return None
    with open(p, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                cfg[k.strip()] = v.strip()
    return cfg

# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------
PRIVATE_IP_RE = re.compile(
    r'(127\.\d+\.\d+\.\d+)'
    r'|(10\.\d+\.\d+\.\d+)'
    r'|(172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)'
    r'|(192\.168\.\d+\.\d+)'
)
PUBLIC_IP_RE = re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b')
API_KEY_RE = re.compile(r'[A-Za-z0-9]{32,}')

def redact_ip(msg):
    def _replace(m):
        ip = m.group(0).split(":")[0]
        if PRIVATE_IP_RE.match(ip):
            return "[local]"
        return "[external]"
    return PUBLIC_IP_RE.sub(_replace, msg)

def redact_message(msg, cfg):
    msg = API_KEY_RE.sub("[REDACTED]", msg)
    msg = redact_ip(msg)
    return msg

def redact_frame(frame, redact_symbols, cfg):
    allowed = {"file", "line", "function", "exception_type", "message"}
    rec = {}
    for k in allowed:
        v = frame.get(k, "")
        if k == "file" and isinstance(v, str):
            base = os.path.basename(v)
            ln = frame.get("line")
            if ln is not None:
                rec["file"] = "./{}:{}".format(base, ln)
            else:
                rec["file"] = "./" + base
        elif k == "function" and isinstance(v, str) and redact_symbols:
            rec["function"] = hashlib.sha256(v.encode()).hexdigest()[:12]
        elif k == "message" and isinstance(v, str):
            rec["message"] = redact_message(v, cfg)
        else:
            rec[k] = v
    return rec

def build_redacted_stack(frame_list, redact_symbols, cfg):
    frames = []
    for f in frame_list[:50]:
        frames.append(redact_frame(f, redact_symbols, cfg))
    return frames

# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------
def cmd_collect():
    config = parse_config()
    if not config or config.get("enabled", "false").lower() != "true":
        return 0

    if os.path.isfile(os.path.join(".council", "opt-out-telemetry")):
        return 0

    diag_dir = os.path.join(".council", "telemetry", "diagnostics")
    os.makedirs(diag_dir, exist_ok=True)

    seen_hashes = set()
    current_file = None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            print("warning: skipping invalid JSON record", file=sys.stderr)
            continue

        stacktrace = rec.get("stacktrace", [])
        if not isinstance(stacktrace, list):
            print("warning: stacktrace must be a list", file=sys.stderr)
            continue

        error_category = rec.get("error_category")
        if not error_category:
            print("warning: missing error_category", file=sys.stderr)
            continue

        redacted_stack = build_redacted_stack(
            stacktrace,
            config.get("redact_symbols", "false").lower() == "true",
            config,
        )

        out_rec = {
            "schema_version": 1,
            "session_id": rec.get("session_id", ""),
            "timestamp": rec.get("timestamp", ""),
            "error_category": error_category,
            "redacted_stack": redacted_stack,
        }

        stacktrace_hash = hashlib.sha256(
            json.dumps(out_rec, sort_keys=True, default=str).encode()
        ).hexdigest()

        out_rec["stacktrace_hash"] = stacktrace_hash

        if stacktrace_hash in seen_hashes:
            continue
        seen_hashes.add(stacktrace_hash)

        try:
            if current_file is None:
                ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
                fname = "events_{}.jsonl".format(ts)
                current_file = os.path.join(diag_dir, fname)

            line_bytes = json.dumps(out_rec, default=str).encode("utf-8") + b"\n"

            cfg_max = config.get("max_file_size_mb", "10")
            try:
                max_bytes = int(float(cfg_max)) * 1024 * 1024
            except (ValueError, TypeError):
                max_bytes = 0

            if max_bytes > 0 and os.path.isfile(current_file):
                if os.path.getsize(current_file) + len(line_bytes) > max_bytes:
                    print(
                        "warning: file size limit reached, creating new file",
                        file=sys.stderr,
                    )
                    ts = datetime.datetime.now(datetime.timezone.utc).strftime(
                        "%Y%m%dT%H%M%S"
                    )
                    fname = "events_{}.jsonl".format(ts)
                    current_file = os.path.join(diag_dir, fname)

            with open(current_file, "ab") as f:
                f.write(line_bytes)
        except Exception as exc:
            print("warning: write error: {}".format(exc), file=sys.stderr)
            continue

    try:
        cfg_max_dir = config.get("max_total_dir_mb", "50")
        try:
            max_dir_bytes = int(float(cfg_max_dir)) * 1024 * 1024
        except (ValueError, TypeError):
            max_dir_bytes = 0

        if max_dir_bytes > 0:
            all_f = sorted(glob.glob(os.path.join(diag_dir, "*.jsonl")))
            total = sum(
                os.path.getsize(f) for f in all_f if os.path.isfile(f)
            )
            for f in all_f:
                if total <= max_dir_bytes:
                    break
                total -= os.path.getsize(f)
                os.remove(f)
                print("warning: rotated old diagnostic file", file=sys.stderr)
    except Exception as exc:
        print("warning: rotation error: {}".format(exc), file=sys.stderr)

    return 0

# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------
def cmd_inspect():
    diag_dir = os.path.join(".council", "telemetry", "diagnostics")
    if not os.path.isdir(diag_dir):
        print("Telemetry: no data collected yet (0 records).")
        return 0

    total = 0
    categories = {}
    total_size = 0
    last_ts = None

    for fn in sorted(os.listdir(diag_dir)):
        fp = os.path.join(diag_dir, fn)
        if not os.path.isfile(fp):
            continue
        total_size += os.path.getsize(fp)
        with open(fp, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    total += 1
                    cat = rec.get("error_category", "unknown")
                    categories[cat] = categories.get(cat, 0) + 1
                    ts = rec.get("timestamp")
                    if ts:
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                except (json.JSONDecodeError, ValueError):
                    continue

    print("Telemetry summary")
    print("  Record count: {}".format(total))
    if total_size >= 1024:
        print("  Directory size: {:.1f} KiB ({} bytes)".format(
            total_size / 1024, total_size))
    else:
        print("  Directory size: {} bytes".format(total_size))
    if last_ts:
        print("  Last record: {}".format(last_ts))
    for cat, cnt in sorted(categories.items()):
        print("  {}: {}".format(cat, cnt))

    return 0

# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------
def cmd_bundle():
    diag_dir = os.path.join(".council", "telemetry", "diagnostics")
    manifest_files = []

    if os.path.isdir(diag_dir):
        manifest_files = sorted(
            os.path.relpath(
                os.path.join(diag_dir, f), ".council/telemetry"
            )
            for f in os.listdir(diag_dir)
            if f.endswith(".jsonl")
        )

    manifest = {
        "schema_version": 1,
        "collector_version": "0.1.0",
        "project_name": "",
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "files": list(manifest_files),
    }

    config = parse_config()
    if config:
        manifest["project_name"] = config.get("project_name", "")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as mf:
        mf.write(json.dumps(manifest, indent=2).encode("utf-8"))
        manifest_path = mf.name

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tf:
            tar_path = tf.name

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(manifest_path, arcname="manifest.json")
            for fpath in manifest_files:
                full = os.path.join(".council", "telemetry", fpath)
                if os.path.isfile(full):
                    tar.add(full, arcname=fpath)

        with open(tar_path, "rb") as f:
            sys.stdout.buffer.write(f.read())
    finally:
        os.unlink(manifest_path)
        if os.path.exists(tar_path):
            os.unlink(tar_path)

    return 0

# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def cmd_read(bundle_path):
    try:
        tmpdir = tempfile.mkdtemp()
        with tarfile.open(bundle_path, "r:gz") as tar:
            members = tar.getmembers()

            # Security: reject absolute paths and path traversal
            safe_names = {"manifest.json"}
            for fpath in members:
                if fpath.isabs():
                    print(
                        "warning: skipping member with absolute path: {}".format(
                            fpath.name), file=sys.stderr)
                    continue
                norm = os.path.normpath(fpath.name)
                if norm.startswith("..") or norm.startswith("/"):
                    print(
                        "warning: skipping path-traversal member: {}".format(
                            fpath.name), file=sys.stderr)
                    continue
                safe_names.add(norm)

            # Only extract manifest.json + files from manifest (validated)
            safe_members = [m for m in members
                            if os.path.normpath(m.name) in safe_names]

            for m in safe_members:
                tar.extract(m, tmpdir)
    except Exception:
        print("warning: could not extract bundle", file=sys.stderr)
        return 0

    manifest_path = os.path.join(tmpdir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print("warning: no manifest in bundle", file=sys.stderr)
        return 0

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except Exception:
        print("warning: invalid manifest", file=sys.stderr)
        return 0

    schema = manifest.get("schema_version")
    if schema != 1:
        print(
            "warning: unsupported schema_version {}, skipping files".format(
                schema
            ),
            file=sys.stderr,
        )
        return 0

    for fpath in manifest.get("files", []):
        print(fpath)

    return 0

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print("Usage: collect_telemetry.sh [OPTIONS]")
        print("")
        print("Options:")
        print("  --collect        Collect error records from stdin JSONL (default)")
        print("  --inspect        Print telemetry summary (no record content)")
        print("  --bundle         Write gzip-tar bundle to stdout")
        print("  --read <file>    Read and list files from a bundle")
        print("  --help           Show the help")
        return 0

    if "--bundle" in args:
        return cmd_bundle()

    if "--inspect" in args:
        return cmd_inspect()

    if "--read" in args:
        idx = args.index("--read")
        if idx + 1 < len(args):
            return cmd_read(args[idx + 1])
        print(
            "warning: --read requires a file path", file=sys.stderr
        )
        return 0

    return cmd_collect()

sys.exit(main())
PY

exec python3 "$_PYTHON_TMP" "$@"
