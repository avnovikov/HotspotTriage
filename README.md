# HotspotTriage (`hotspottriage`)

A Python port of [`code-complexity`](https://github.com/simonrenoult/code-complexity) using real Python AST metrics (via [`radon`](https://github.com/rubik/radon)) instead of degrading to line counts.

For each tracked Python file in a git repo, it computes:

| metric            | what                                                                       |
|-------------------|----------------------------------------------------------------------------|
| `sloc`            | source lines (no blanks/comments)                                          |
| `cyclomatic`      | sum of McCabe complexity across all functions/methods/classes              |
| `halstead`        | Halstead volume                                                            |
| `maintainability` | `100 - radon's MI` (so higher = worse, like the others)                    |
| `churn`           | total lines added + deleted across all commits (binary files excluded)     |
| `churn_per_sloc`  | `churn / sloc` — instability normalized by file size                       |
| `score`           | product of the metrics passed via `-s` (default: `churn_per_sloc × cyclomatic`) |

`churn_per_sloc` removes the size effect from raw lines-changed: a small file rewritten many times gets a higher signal than a big file edited once. The default score `churn_per_sloc × cyclomatic` ≈ "how unstable is this file × how tangled is its control flow" — the classic refactor target.

## Usage

```bash
uv run hotspottriage <repo> [options]

  --filter <globs>             comma-separated; AND semantics (e.g. 'src/**,!**/tests/**')
  --no-default-filter          disable the implicit **/*.py filter
  -s, --score <metrics>        comma-separated metrics whose product is the score
                                metrics: sloc, cyclomatic, halstead, maintainability, churn, churn_per_sloc
                                default: churn_per_sloc,cyclomatic
  -f, --format                 table | json | csv  (default: table)
  -l, --limit <N>
  -i, --since <date>           passed to git log
  -u, --until <date>           passed to git log
  --sort                       score | file  (default: score)
  -d, --directories            aggregate by directory
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
  - churn_per_sloc
  - cyclomatic
format: table                    # table | json | csv
limit: null                      # max rows (null = unlimited)
sort: score                      # score | file
granularity: file                # file | block
since: null                      # git --since (any date string git accepts)
until: null                      # git --until
directories: false               # aggregate by directory; not allowed with granularity: block
ignore_directories: []           # POSIX prefixes under the repo to skip entirely, e.g. ['vendor', 'generated']
respect_gitignore: true         # apply .gitignore, **/.gitignore, and .git/info/exclude to tracked paths
block_workers: null              # block-churn thread pool size
cache_dir: null                  # null = $XDG_CACHE_HOME or ~/.cache
log_level: warning               # debug | info | warning | error
```

### Ignores (gitignore + directories)

After `git ls-files` returns tracked paths, HotspotTriage applies, in order:

1. **Glob filter** — `--filter` / `filter` plus the implicit `**/*.py` unless disabled.
2. **Directory prefixes** — `ignore_directories` in YAML and/or repeated `--ignore-dir`. Any path equal to a prefix or under `prefix/` is dropped (prefixes are normalised POSIX paths; `..` is rejected).
3. **Gitignore rules** — unless `respect_gitignore: false` or `--no-respect-gitignore`: root `.gitignore`, `.git/info/exclude`, then each nested `.gitignore` along the path to the file, in git’s usual order. Last matching pattern wins, including `!` negation. This matches how git would treat an **untracked** file, but is applied to **tracked** paths so accidentally-committed ignored trees can be excluded from the report.

### Skipping config files

```bash
# Pure-CLI mode (ignores every config file; useful in CI / scripts)
uv run hotspottriage <repo> --no-config

# Use a one-off file instead of the standard layers
uv run hotspottriage <repo> --config /path/to/team.yml
```
