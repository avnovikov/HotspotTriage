# HotspotTriage (`hotspottriage`)

A Python port of [`code-complexity`](https://github.com/simonrenoult/code-complexity) using real Python AST metrics (via [`radon`](https://github.com/rubik/radon)) instead of degrading to line counts.

**Requires Python 3.11+** (up to 3.13 per `requires-python` in `pyproject.toml`), mainly because optional block similarity uses [`deepcsim`](https://pypi.org/project/deepcsim/).

For each tracked Python file in a git repo, it computes:

| metric            | what                                                                       |
|-------------------|----------------------------------------------------------------------------|
| `sloc`            | source lines (no blanks/comments)                                          |
| `cyclomatic`      | sum of McCabe complexity across all functions/methods/classes              |
| `halstead`        | Halstead volume                                                            |
| `maintainability` | `100 - radon's MI` (so higher = worse, like the others)                    |
| `churn`           | total lines added + deleted across all commits (binary files excluded)     |
| `churn_per_sloc`  | `churn / sloc` — instability normalized by file size                       |
| `decayed_churn`   | churn with exponential decay by file age (see `decay_half_life` in config) |
| `decayed_churn_per_sloc` | `decayed_churn / sloc`                                                |
| `smell_count`     | total smell occurrences in the row’s scope (file or block)               |
| `smells`          | JSON map: `smell_id → count` (e.g. `long_method`, `long_parameter_list`)   |
| `similarity_score` | max DeepCSIM composite similarity (0–100) vs other blocks; **0** in file mode, when similarity is **off** (`similarity_band` **`off`**), with a single block, or when no snippet yields metrics |
| `similarity_band` | `none` \| `low` \| `medium` \| `high` \| `aggregate` (synthetic summary row) \| **`off`** (block mode, `--no-similarity` / `similarity_enabled: false`) \| **`n/a`** (file mode) |
| `match_count`     | other blocks at or above `similarity_threshold`; **0** in file mode or when similarity is off |
| `score`           | product of the metrics passed via `-s` (default: `decayed_churn_per_sloc × cyclomatic`) |

`churn_per_sloc` removes the size effect from raw lines-changed: a small file rewritten many times gets a higher signal than a big file edited once. The default score `decayed_churn_per_sloc × cyclomatic` weights recent churn and control-flow complexity (see `decay_half_life` in config).

## Usage

```bash
uv run hotspottriage <repo> [options]

  --filter <globs>             comma-separated; AND semantics (e.g. 'src/**,!**/tests/**')
  --no-default-filter          disable the implicit **/*.py filter
  -s, --score <metrics>        comma-separated metrics whose product is the score
                                metrics: sloc, cyclomatic, halstead, maintainability, churn, churn_per_sloc,
                                         decayed_churn, decayed_churn_per_sloc, smell_count, similarity_score (block only)
                                default: decayed_churn_per_sloc,cyclomatic
  --progress / --no-progress   Rich progress on stderr (config: progress; null = TTY auto)
  --similarity / --no-similarity  DeepCSIM block similarity (on by default for --blocks; config: similarity_enabled)
  -f, --format                 table | json | csv  (default: table)
  -l, --limit <N>
  -i, --since <date>           passed to git log
  -u, --until <date>           passed to git log
  --sort                       score | file  (default: score)
  -d, --directories            aggregate by directory
  -B, --blocks                 per function/method/async def (same as --granularity block)
  --granularity                file | block  (default: file)
  --ignore-dir <PREFIX>        repeatable; drop tracked paths under this POSIX prefix
  --no-respect-gitignore       skip .gitignore / nested .gitignore / .git/info/exclude when filtering
```

Supports local paths and remote git URLs (cloned to a temp dir).

By default, **gitignore rules apply to tracked paths** (so vendored or generated trees listed in `.gitignore` are skipped even if they were committed once). Use `--no-respect-gitignore` to analyse every tracked file that passes the glob filter. Combine with `--ignore-dir vendor` (repeatable) or the `ignore_directories` config list to exclude whole directory prefixes.

### Examples

```bash
# Default: rank by churn × cyclomatic
uv run hotspottriage ~/myrepo

# Just sort by cyclomatic alone
uv run hotspottriage ~/myrepo -s cyclomatic -l 20

# Find files that are unmaintainable AND churned
uv run hotspottriage ~/myrepo -s churn,maintainability -l 20

# Triple-product
uv run hotspottriage ~/myrepo -s churn,cyclomatic,maintainability

# Dump everything to CSV
uv run hotspottriage ~/myrepo -f csv > complexity.csv

# Aggregate by directory
uv run hotspottriage ~/myrepo -d -l 10

# Per-function/method analysis (cached under .hotspottriage/cache/)
uv run hotspottriage ~/myrepo --blocks -s cyclomatic -l 10
# equivalent: --granularity block

# Same, plus AST similarity vs other blocks (DeepCSIM) and stderr progress
uv run hotspottriage ~/myrepo --blocks --similarity --progress -f json

# Optional: include similarity in the score product (block mode only)
uv run hotspottriage ~/myrepo --blocks --similarity -s decayed_churn_per_sloc,cyclomatic,similarity_score
```

The output always contains every metric, so a single CSV dump can be re-sorted later by any column you like.

## Configuration

HotspotTriage supports layered YAML configuration, modeled after [Serena](https://github.com/oraios/serena). Settings resolve in this order (last wins):

1. Built-in code defaults
2. **Global** — `~/.hotspottriage/config.yml`
3. **Project** — `<repo>/.hotspottriage/project.yml` (versioned)
4. **Project local** — `<repo>/.hotspottriage/project.local.yml` (gitignored, per-machine)
5. **Explicit** — file passed via `--config <PATH>`
6. **CLI flags** — only when explicitly passed

A layer needs to specify only the keys it wants to override; everything else falls through.

### Scaffolding config files

```bash
# Write a commented template at ~/.hotspottriage/config.yml
uv run hotspottriage init --global

# Inside a repo: create <repo>/.hotspottriage/{project.yml, project.local.yml, .gitignore}
uv run hotspottriage init --project
```

### Available keys

```yaml
filter: []                       # default filter globs (CLI --filter overrides)
no_default_filter: false         # set true to disable the implicit **/*.py filter
score_metrics:                   # metrics whose product is the `score` column
  - decayed_churn_per_sloc
  - cyclomatic
smell_weight: 0.0                # used when score_metrics includes smell_count (factor: 1 + smell_weight * smell_count)
format: table                    # table | json | csv
limit: null                      # max rows (null = unlimited)
sort: score                      # score | file
granularity: file                # file | block
since: null                      # git --since (any date string git accepts)
until: null                      # git --until
directories: false               # aggregate by directory; not allowed with granularity: block
ignore_directories: []           # POSIX prefixes under the repo to skip entirely, e.g. ['vendor', 'generated']
respect_gitignore: true         # apply .gitignore, **/.gitignore, and .git/info/exclude to tracked paths
block_workers: null              # block-churn thread pool size (default: 16)
log_level: warning               # debug | info | warning | error
decay_half_life: 2592000        # seconds; null disables churn decay (see built-in defaults)
progress: null                   # null = stderr TTY auto | true | false
# Block-only similarity (DeepCSIM): similarity_enabled, similarity_threshold,
# similarity_band_* , similarity_max_pairwise_blocks, similarity_aggregate_row
```

## MCP tools

The MCP server exposes analysis tools plus smell retrieval:

- `analyze(...)`
- `analyze_with_cache(...)`
- `analyze_classes(...)`
- `generate_cache(...)`
- `cache_status(...)`
- `clear_cache(...)`
- `init_config(...)`
- `get_code_smells(...)` → flat findings: `{file, line, smell, message, confidence?, scope?}`
- `analyze(..., similarity: bool = true)` / `analyze_with_cache(..., similarity: bool = true)` → set `similarity_enabled` for block runs (file granularity ignores it)

### Ignores (gitignore + directories)

After `git ls-files` returns tracked paths, HotspotTriage applies, in order:

1. **Glob filter** — `--filter` / `filter` plus the implicit `**/*.py` unless disabled.
2. **Directory prefixes** — `ignore_directories` in YAML and/or repeated `--ignore-dir`. Any path equal to a prefix or under `prefix/` is dropped (prefixes are normalised POSIX paths; `..` is rejected).
3. **Gitignore rules** — unless `respect_gitignore: false` or `--no-respect-gitignore`: root `.gitignore`, `.git/info/exclude`, then each nested `.gitignore` along the path to the file, in git’s usual order. Last matching pattern wins, including `!` negation. This matches how git would treat an **untracked** file, but is applied to **tracked** paths so accidentally-committed ignored trees can be excluded from the report.

### Block-level granularity and caching

When `--blocks` or `--granularity block` is used, HotspotTriage computes metrics for each function, method, and async function (not class rows). The first run computes churn via `git log -L` for each block; subsequent runs reuse cached values in `<repo>/.hotspottriage/cache/blocks.pkl`, keyed by file blob SHA so changes invalidate automatically.

**Smells on block rows:** a finding is attached to a block when its Pylint `line` lies inside that block’s line range. Class-level messages (e.g. too many attributes on the `class` line) carry a `scope` marker so they are also counted on every method block under that class (`Foo.bar`, `Foo.Inner.baz`, …), not only on the class definition line. Module-wide comment smells stay on whichever block contains their reported line (often line 1). The `smells` column on each row is `{smell_id: count}` (no free-text messages).

**Block similarity ([DeepCSIM](https://pypi.org/project/deepcsim/)):** With `--blocks`, similarity runs **by default** (`similarity_enabled: true` in defaults). Use **`--no-similarity`** or `similarity_enabled: false` to skip the O(n²) step. Each block row gets `similarity_score` (best composite match vs other blocks), `similarity_band`, and `match_count` (peers ≥ `similarity_threshold`). Very large block counts switch to hash-only clustering (see `similarity_max_pairwise_blocks`). When `similarity_aggregate_row` is true, a final synthetic row `__aggregate_similarity__::repo` summarizes the run (mean score, pair counts, mode); it is sorted after normal rows and excluded from directory aggregation.

#### Cache metadata and timestamps

Cache metadata is stored in `<repo>/.hotspottriage/cache/metadata.json` and includes:
- **generated_at**: Unix timestamp when cache was created
- **entry_count**: Number of cached entries
- **version**: Cache format version
- **file_timestamps** (optional): Per-file analysis metadata including:
  - **last_commit_timestamp**: Unix timestamp of last commit touching this file
  - **analysis_timestamp**: Unix timestamp when metrics were computed
  - **blob_sha**: Git object hash at analysis time (detects code changes)

This enables:
- Detecting when cached metrics are stale (by comparing file blob SHAs)
- Calculating deltas between cache versions (added/changed/deleted files)
- Estimating cache age and freshness

Add `.hotspottriage/` to your `.gitignore` to avoid committing cached data:

```bash
echo '.hotspottriage/' >> .gitignore
```

### Skipping config files

```bash
# Pure-CLI mode (ignores every config file; useful in CI / scripts)
uv run hotspottriage <repo> --no-config

# Use a one-off file instead of the standard layers
uv run hotspottriage <repo> --config /path/to/team.yml
```

### uv lockfile

If you use **`uv`** for development, run **`uv lock`** after editing `pyproject.toml` dependencies so `uv.lock` matches (the GitHub workflow installs with `pip install -e .` and does not require an up-to-date lock).
