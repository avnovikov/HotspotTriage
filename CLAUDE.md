# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HotspotTriage** (`hotspottriage`) ranks Python code by complexity × churn. It's a Python port of [code-complexity](https://github.com/simonrenoult/code-complexity) using real AST metrics from [`radon`](https://github.com/rubik/radon) instead of line counts.

For each tracked `.py` file in a git repo, it computes:
- **sloc**: source lines (excluding blanks/comments)
- **cyclomatic**: sum of McCabe complexity across all functions/methods/classes
- **halstead**: Halstead volume
- **maintainability**: `100 - radon's MI` (higher = worse)
- **churn** / **churn_per_sloc**: lines changed across git history; ratio normalizes by size
- **decayed_churn** / **decayed_churn_per_sloc**: churn weighted by file age (`decay_half_life`)
- **smell_count** / **smells**: Pylint + heuristic code smells (`smell.py`); `smells` is `{id: count}` on each row
- **similarity_score** / **similarity_band** / **match_count**: DeepCSIM block similarity (on by default for block granularity; use `--no-similarity` / `similarity_enabled: false` to skip)
- **score**: product of user-selected metrics (default: `decayed_churn_per_sloc × cyclomatic`)

The default scoring targets refactor hotspots: files that are both unstable (frequently rewritten) and tangled (high cyclomatic complexity).

## Architecture

### Data Flow

1. **Discovery** (`discovery.py`): Find all tracked `.py` files via `git ls-files`
2. **Filtering** (`filtering.py`): Apply glob patterns (AND semantics) and directory prefixes; optionally apply `.gitignore` rules (to exclude accidentally-committed ignored trees)
3. **Metrics Collection**:
   - **Complexity** (`complexity.py`): Uses `radon` to extract AST metrics (sloc, cyclomatic, halstead, maintainability)
   - **Churn** (`churn.py`): Uses `git log` to compute lines added/deleted per file
   - **Block Churn** (`block_churn.py`): For `--granularity block`, computes churn per function/method via `git log -L` with optional caching
   - **Smells** (`smell.py`): Pylint JSON + radon/comment heuristics + approximate class smells; rollups attach to `Statistic`
   - **Block similarity** (`block_similarity.py`): DeepCSIM pairwise similarity over block snippets (default on for block runs)
4. **Stats** (`stats.py`): Aggregates metrics into `Statistic` dataclasses; applies sorting, limiting, and score calculation
5. **Normalize** (`normalize.py`): Optional per-metric maps to ``[0,1]`` (``metric_normalization`` in config); ``normalize`` / ``normalize_record`` APIs
6. **Output** (`output.py`): Formats results as table/JSON/CSV; appends ``norm_<metric>`` columns when ``metric_normalization`` is present in merged config

Optional **stderr progress** (`progress_report.py` + CLI `--progress`) runs alongside steps 3–4 without affecting stdout (table/CSV/JSON).

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
| `smell.py` | Code-smell detection (Pylint + radon/comments + approximate class smells); `finding_applies_to_block` for block rows |
| `block_similarity.py` | DeepCSIM integration: per-block `similarity_score`, bands, `match_count`; repo aggregate row |
| `stats.py` | `Statistic` dataclass; aggregation (file vs. directory); sorting by score/file; limiting |
| `normalize.py` | Configurable metric normalization (zscore, piecewise, inverse_piecewise, identity) to ``[0,1]`` |
| `score.py` | Block-level aggregated risk score (0–1), subscores, bands; weights under ``score_aggregation`` |
| `output.py` | Formatting: table (tabulate), JSON, CSV |
| `progress_report.py` | Rich stderr progress bar (optional; config `progress`) |
| `mcp_server.py` | FastMCP server: analyze, analyze_with_cache, get_code_smells, analyze_classes, generate_cache, cache_status, clear_cache, init_config |
| `cache_generator.py` | Comprehensive cache generation combining block-level metrics and class/method structure analysis |

### Granularity Modes

- **file**: One row per Python file (default, fast)
- **block**: One row per function/method/async function (slower, uses cached block churn from `git log -L`)

Block-level caching stores results in `.hotspottriage/cache/blocks.pkl`, keyed by file blob SHA, so cache invalidates automatically when file content changes.

## Development Commands

All commands use `uv` (fast Python package manager; see `pyproject.toml`). After changing dependencies, run **`uv lock`** so `uv.lock` stays aligned.

### Install & Run
```bash
# Install the tool in editable mode
uv sync

# Run the tool on any git repo
uv run hotspottriage <repo> [options]

# Run on the repo itself (for testing)
uv run hotspottriage .

# Generate comprehensive cache (blocks + classes)
uv run hotspottriage-cache <repo> [--filter GLOBS] [--score METRICS]

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

The FastMCP server (`mcp_server.py`) exposes HotspotTriage as an MCP tool for Claude and other AI assistants.

### Available MCP Tools

- **`analyze(target, ...options)`**: Run repository analysis; returns JSON list of `Statistic` objects (file or block granularity). `similarity` defaults to true for block runs; pass `similarity=False` to skip DeepCSIM.

- **`analyze_with_cache(target, ...options)`**: Block-level analysis with cache generation in `<repo>/.hotspottriage/cache/blocks.pkl`. `similarity` defaults to true; pass `similarity=False` to skip.

- **`get_code_smells(target, ...)`**: Flat smell findings per tracked file (`file`, `line`, `smell`, `message`, optional `confidence` / `scope`).

- **`analyze_classes(target, filter)`**: Extract and analyze class and method definitions. Returns file/class/method hierarchy with line ranges.

- **`generate_cache(target, filter, score_metrics)`**: Generate comprehensive codebase cache including blocks, classes, and metrics. Returns cache statistics.

- **`cache_status(target)`**: Check cache statistics (directory, entry count, file size).

- **`clear_cache(target)`**: Clear the block-level cache for a repository.

- **`init_config(target, is_global)`**: Scaffold config files at `<repo>/.hotspottriage/` or `~/.hotspottriage/`

### Cache Architecture

The caching system is separated into two functions:

- **`_initialize_repository()`**: Pure cache warming function that computes block-level metrics and stores in cache. Returns cache statistics only (no analysis results).

- **`_analyze_repository()`**: Queries metrics with optional caching for block granularity. Returns full analysis results.

This separation allows efficient cache warming (just store, don't return) and flexible querying (with or without cache).

All tools return JSON-formatted results. The server reuses CLI logic (config, filtering, metrics) for consistency.

## Testing Fixtures

The `tests/fixtures/` directory contains small test git repos with known structure and commit history, used to validate metrics computation in isolation from the main repo.

## Notes

- **Python 3.11+** required (`requires-python` in `pyproject.toml`; `deepcsim` caps below 3.14).
- The tool respects `.gitignore` by default (applies to **tracked** files to exclude accidentally-committed ignored trees). Use `--no-respect-gitignore` to analyze all tracked files.
- **No network required** once the repo is local; can analyze remote git URLs (cloned to temp dir).
- **Performance**: File-level analysis is fast; block-level analysis is slower (uses `git log -L` per function). Caching makes subsequent block-level runs instant.
