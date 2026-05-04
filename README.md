# code-complexity-py

A Python port of [`code-complexity`](https://github.com/simonrenoult/code-complexity) that uses real Python AST metrics (via [`radon`](https://github.com/rubik/radon)) instead of degrading to line counts.

For each tracked Python file in a git repo, computes:

- **complexity** — McCabe cyclomatic (default), Halstead volume, raw SLOC, or maintainability index
- **churn** — number of commits touching the file
- **score** — `complexity × churn` — high score = complex *and* often-changed, prime refactor candidates

## Usage

```bash
uv run code-complexity-py <repo> [options]

  --filter <globs>             comma-separated; AND semantics (e.g. 'src/**,!**/tests/**')
  -cs, --complexity-strategy   sloc | cyclomatic | halstead | maintainability  (default: cyclomatic)
  -f,  --format                table | json | csv  (default: table)
  -l,  --limit <N>
  -i,  --since <date>          passed to git log
  -u,  --until <date>          passed to git log
  -s,  --sort                  score | churn | complexity | file  (default: score)
  -d,  --directories           aggregate by directory
       --no-default-filter     disable the implicit **/*.py filter
```

Supports local paths and remote git URLs (cloned to a temp dir).
