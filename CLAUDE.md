# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HotspotTriage** (`hotspottriage`) ranks Python code by complexity × churn. It's a Python port of [code-complexity](https://github.com/simonrenoult/code-complexity) using real AST metrics from [`radon`](https://github.com/rubik/radon) instead of line counts.

For each tracked `.py` file in a git repo, it computes:
- **sloc**: source lines (excluding blanks/comments)
- **cyclomatic**: sum of McCabe complexity across all functions/methods/classes
- **halstead**: Halstead volume
- **maintainability**: `100 - radon's MI` (higher = worse)
- **churn**: total lines added + deleted across commits
- **churn_per_sloc**: `churn / sloc` — instability normalized by file size
- **score**: product of user-selected metrics (default: `churn_per_sloc × cyclomatic`)

The default scoring targets refactor hotspots: files that are both unstable (frequently rewritten) and tangled (high cyclomatic complexity).

## Architecture

### Data Flow

1. **Discovery** (`discovery.py`): Find all tracked `.py` files via `git ls-files`
2. **Filtering** (`filtering.py`): Apply glob patterns (AND semantics) and directory prefixes; optionally apply `.gitignore` rules (to exclude accidentally-committed ignored trees)
3. **Metrics Collection**:
   - **Complexity** (`complexity.py`): Uses `radon` to extract AST metrics (sloc, cyclomatic, halstead, maintainability)
   - **Churn** (`churn.py`): Uses `git log` to compute lines added/deleted per file
   - **Block Churn** (`block_churn.py`): For `--granularity block`, computes churn per function/method via `git log -L` with optional caching
4. **Stats** (`stats.py`): Aggregates metrics into `Statistic` dataclasses; applies sorting, limiting, and score calculation
5. **Output** (`output.py`): Formats results as table/JSON/CSV

### Configuration System

Settings resolve in this order (last wins):
1. Code DEFAULTS (`config.DEFAULTS`)
2. Global `~/.hotspottriage/config.yml`
3. Project `<repo>/.hotspottriage/project.yml` (versioned)
4. Project local `<repo>/.hotspottriage/project.local.yml` (gitignored, per-machine)
5. Explicit `--config <PATH>`
6. CLI flags (only when explicitly passed)

The `init` subcommand scaffolds `.hotspottriage/` with example configs. Config keys are validated against `config.DEFAULTS` so invalid settings raise clear errors.

### Key Modules

| Module | Responsibility |
|--------|-----------------|
| `cli.py` | Entry point; argparse setup; argument merging with config layers |
| `config.py` | Layered YAML resolution; type validation; scaffold templates |
| `discovery.py` | Git integration (`git ls-files`); tracked file enumeration |
| `filtering.py` | Glob matching (AND semantics, negation); directory prefix filtering; gitignore rule application |
| `complexity.py` | Radon integration; AST metric extraction |
| `churn.py` | `git log` parsing; per-file churn computation |
| `block_churn.py` | `git log -L` for function/method churn; threading; block-level cache invalidation |
| `cache.py` | Pickle-based caching in `.hotspottriage/cache/`; SHA-keyed so changes auto-invalidate |
| `blocks.py` | AST traversal to identify functions, methods, async functions; compute per-block metrics |
| `stats.py` | `Statistic` dataclass; aggregation (file vs. directory); sorting by score/file; limiting |
| `output.py` | Formatting: table (tabulate), JSON, CSV |
| `mcp_server.py` | FastMCP server exposing analyze and init_config as MCP tools |

### Granularity Modes

- **file**: One row per Python file (default, fast)
- **block**: One row per function/method/async function (slower, uses cached block churn from `git log -L`)

Block-level caching stores results in `.hotspottriage/cache/blocks.pkl`, keyed by file blob SHA, so cache invalidates automatically when file content changes.

## Development Commands

All commands use `uv` (fast Python package manager; see `pyproject.toml`).

### Install & Run
```bash
# Install the tool in editable mode
uv sync

# Run the tool on any git repo
uv run hotspottriage <repo> [options]

# Run on the repo itself (for testing)
uv run hotspottriage .

# Run the MCP server
uv run hotspottriage-mcp
```

### Testing
```bash
# Run all tests
uv run pytest

# Run a specific test file
uv run pytest tests/test_cli.py

# Run a specific test
uv run pytest tests/test_cli.py::test_analyze_with_limit

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=src/hotspottriage
```

Tests live in `tests/` and use pytest fixtures (see `tests/fixtures/` for test repos). The test structure mirrors `src/hotspottriage/` (e.g., `test_config.py` tests `src/hotspottriage/config.py`).

### Debugging
```bash
# Enable debug logging (see config.log_level)
uv run hotspottriage . --log-level debug

# Run Python in the project's virtual environment
uv run python
```

## MCP Server Integration

The FastMCP server (`mcp_server.py`) exposes HotspotTriage as an MCP tool for Claude and other AI assistants. It provides two tools:

- **`analyze(target, ...options)`**: Run full repository analysis, returns JSON list of `Statistic` objects
- **`init_config(target, is_global)`**: Scaffold config files at `<repo>/.hotspottriage/` or `~/.hotspottriage/`

The server reuses CLI logic (config merging, filtering, metrics computation) so both interfaces are consistent.

## Testing Fixtures

The `tests/fixtures/` directory contains small test git repos with known structure and commit history, used to validate metrics computation in isolation from the main repo.

## Notes

- **Python 3.10+** required (uses `match` statements, `|` union types).
- The tool respects `.gitignore` by default (applies to **tracked** files to exclude accidentally-committed ignored trees). Use `--no-respect-gitignore` to analyze all tracked files.
- **No network required** once the repo is local; can analyze remote git URLs (cloned to temp dir).
- **Performance**: File-level analysis is fast; block-level analysis is slower (uses `git log -L` per function). Caching makes subsequent block-level runs instant.
