# code-complexity-py

A Python port of [`code-complexity`](https://github.com/simonrenoult/code-complexity) using real Python AST metrics (via [`radon`](https://github.com/rubik/radon)) instead of degrading to line counts.

For each tracked Python file in a git repo, it computes:

| metric            | what                                                                  |
|-------------------|-----------------------------------------------------------------------|
| `sloc`            | source lines (no blanks/comments)                                     |
| `cyclomatic`      | sum of McCabe complexity across all functions/methods/classes         |
| `halstead`        | Halstead volume                                                       |
| `maintainability` | `100 - radon's MI` (so higher = worse, like the others)               |
| `churn`           | number of commits touching the file                                   |
| `score`           | product of the metrics passed via `-s` (default: `churn × cyclomatic`) |

The point of `score` is to find files that are bad along *several* axes at once. The classic refactor candidate is high `churn × cyclomatic`: complex *and* changed often.

## Usage

```bash
uv run code-complexity-py <repo> [options]

  --filter <globs>             comma-separated; AND semantics (e.g. 'src/**,!**/tests/**')
  --no-default-filter          disable the implicit **/*.py filter
  -s, --score <metrics>        comma-separated metrics whose product is the score
                                metrics: sloc, cyclomatic, halstead, maintainability, churn
                                default: churn,cyclomatic
  -f, --format                 table | json | csv  (default: table)
  -l, --limit <N>
  -i, --since <date>           passed to git log
  -u, --until <date>           passed to git log
  --sort                       score | file  (default: score)
  -d, --directories            aggregate by directory
```

Supports local paths and remote git URLs (cloned to a temp dir).

### Examples

```bash
# Default: rank by churn × cyclomatic
uv run code-complexity-py ~/myrepo

# Just sort by cyclomatic alone
uv run code-complexity-py ~/myrepo -s cyclomatic -l 20

# Find files that are unmaintainable AND churned
uv run code-complexity-py ~/myrepo -s churn,maintainability -l 20

# Triple-product
uv run code-complexity-py ~/myrepo -s churn,cyclomatic,maintainability

# Dump everything to CSV
uv run code-complexity-py ~/myrepo -f csv > complexity.csv

# Aggregate by directory
uv run code-complexity-py ~/myrepo -d -l 10
```

The output always contains every metric, so a single CSV dump can be re-sorted later by any column you like.
