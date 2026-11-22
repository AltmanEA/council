# Council Host Runbook

Operational procedure for installing and maintaining the Council framework in a
host project via the `dist/` channel. This runbook is the single operational
reference for the host operator; read it before the first install.

Framework model (per `sess-tooling-separation-2026-11-22`): the source repo
develops tools **edit-in-place**; a host project receives a **pinned snapshot**
of a tagged release via `dist/`. The host never edits Council (core) files in
place — improvements go through the source repo and arrive with the next update.

---

## 1. Before installing: choose the mode

| Situation | Mode |
|-----------|------|
| New, empty directory for the host project | `init` |
| Existing project directory (code/docs already there) | `overlay` |

- `init` creates the project skeleton, runs `git init` if needed, installs core + templates.
- `overlay` adds Council **without overwriting existing files** (`SKIP (exists)`
  lines in the output are normal — but review them to confirm the templates you
  expected actually got installed).

Checklist: new directory → `init`; existing project → `overlay`.

## 2. Install

From the unpacked distribution directory:

```bash
tar xzf council-dist-<VERSION>.tar.gz
cd council-dist
bash install.sh --target /path/to/host --mode <init|overlay> --project-name <name>
```

Then, if git is available (advisory pre-commit audit):

```bash
cd /path/to/host
bash tools/install-hooks.sh
```

Expected output checks:
- `Locked version: <VERSION>` — this is the pinned version;
- `Core manifest: N files`;
- `Updater copied to .council/update.sh`;
- PyYAML missing → WARNING with the list of broken tools; install it
  (`pip install pyyaml`) before running any `tools/*.py`.

If `install.sh` itself goes wrong (init mode wrote files): the host is a git
repo — commit early and recover with `git checkout` / `git revert`. There is no
install-time backup otherwise.

## 3. Check the installed (pinned) version

```bash
cat .council/version.lock          # e.g. "v0.1.0" — do not edit manually
```

`.council/version.lock` is written by `install.sh`/`update.sh` from the release's
`version.txt`. A version starting with `dev-` means the archive was built
without a git tag — it is a test build, do not keep it on a host
(see `dist/README.md` §Releasing).

Version awareness policy (MVP): the operator checks versions manually.
After an update the summary block prints the new version; to see what is newer,
look at the source repo git log / changelogs. There is no subscription or push
notification — the host operator decides when to update.

## 4. Update

Copy **both** files from the build machine (same directory):

- `council-dist-<NEW-VERSION>.tar.gz`
- `SHA256SUMS`

Then, from the host project root:

```bash
bash .council/update.sh /path/to/council-dist-<NEW-VERSION>.tar.gz
```

Behaviour:
- **Integrity:** if `SHA256SUMS` sits next to the archive, the checksum is
  verified automatically before unpacking. On mismatch the update aborts —
  re-copy both files. If the file is missing, a loud WARNING is printed;
  treat that as a procedural error, not a warning to ignore.
- **PyYAML:** update aborts with ERROR if PyYAML is missing (core tools would
  be broken after the update).
- **Backup:** every core file is copied to `.council/backup-<timestamp>/`
  before being overwritten.
- **Removals:** files that were core in the old release but are absent from
  the new one are deleted — each deletion prints the preserved backup path.
  Read the `[removed]` lines; they are not silent.
- Templates (`docs/en/project-concept`, `CHANGELOGS`, host `AGENTS.md`, …) are
  never touched.

## 5. Rollback

After a bad **update** — restore the backup taken by `update.sh` (printed at
the end of its run):

```bash
cp -R .council/backup-<timestamp>/* .
```

Then commit the restoration in the host repo.

## 6. Emergency: an updated core file breaks the host

Procedure (documented deviation from pinned mode):

1. Restore from the latest backup (section 5).
2. If a hotfix is unavoidable to keep working, edit the file in place and
   commit it in the host repo **with a note in the commit message** that this
   is a temporary deviation from pinned mode.
3. Land the real fix in the source repo, release a new tag, and update the
   host normally. The next update overwrites the emergency edit.

## 7. Translation (EN→RU)

The translation engine is shipped in `vendor/techdoc-translator/` and IS used
on hosts. Enable it:

```bash
cd vendor/techdoc-translator
cp .env.example .env
# edit .env: API endpoint / key (OpenAI-compatible or local Ollama)
```

Without `.env` the core framework (docs, audit, manifest) still works; only
EN→RU translation is unavailable.

## 8. Telemetry (opt-in)

The Council framework includes a local, opt-in diagnostics collector
(`tools/collect_telemetry.sh`). No data is collected or transmitted by
default.

### Enable

```bash
bash install.sh --target <dir> --mode init --project-name <name> --enable-telemetry
```

This creates `.council/telemetry.yml` with `enabled: true` and sets up
`diagnostics/` and `metrics/` directories.

### Collected / Not collected

| Item | Collected? |
|------|------------|
| Error records (JSONL) in `diagnostics/` | Yes, when enabled and fed via `--collect` |
| Record count and categories via `--inspect` | Yes (summary only) |
| Bundled export via `--bundle` | Yes (manual, gzip-tar to stdout) |
| Source code, env vars, prompts | No — never transmitted |
| API keys / tokens | No — redacted to `[REDACTED]` |
| Private/loopback IPs | No — redacted to `[local]` |
| Public IPs | No — redacted to `[external]` |

### Opt-out

Create the file `.council/opt-out-telemetry` to prevent all collection:

```bash
touch .council/opt-out-telemetry
```

### Commands

```bash
bash tools/collect_telemetry.sh --collect        # read JSONL from stdin, write to diagnostics/
bash tools/collect_telemetry.sh --inspect         # print summary only
bash tools/collect_telemetry.sh --bundle          # write gzip-tar bundle to stdout
bash tools/collect_telemetry.sh --read <bundle>   # list files from a bundle
```

### Update survival

Telemetry data lives in the host-owned `.council/telemetry/` directory, outside
the core manifest. It survives `update.sh` operations — `update.sh` only manages
core framework files.

### No data leaves the host

- The collector is local and manual; there is no daemon, no network, no TLS.
- `check_all.py` does not initiate telemetry collection.
- The collector is not git-aware — it never touches `.git/` or registers hooks.
- Sampling and scientific validity are the researcher's task, not the
  collector's.

## 9. Test run before the first real host

From the source repo:

```bash
bash dist/test-dry-run.sh          # exit 0 = install → update → restore → overlay OK
```

Run it once after any change to `dist/*.sh`, before shipping an archive to a
real host.

## 10. First release (source repo side)

The pinned channel is anchored to git tags. The first release is tagged
`v0.1.0`:

```bash
git tag v0.1.0
bash dist/build.sh                 # picks VERSION from the tag
```

Without a tag, builds get a `dev-<hash>` version and a warning — testing only.
See `dist/README.md` §Releasing.
