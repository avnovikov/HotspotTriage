# HotspotTriage Scores Explained

This document explains how HotspotTriage computes `score`, how raw metrics are normalized, where values are clipped, and how final risk bands are assigned.

The document focuses on the aggregated scoring path used for interpretable risk in block-level analysis.

---

## Overview

HotspotTriage provides measurable scores for LLM coding agents so they can estimate code complexity, prioritize risky areas, and choose suitable models or review strategies.

**Purpose**: help agents and reviewers answer questions such as:

- How complex is this block?
- How risky is it to modify?
- Should a lighter or stronger model handle this code?
- Which areas deserve more human attention?

**Core flow**:

1. Compute raw metrics with Radon and related inputs
2. Convert them into normalized burdens
3. Combine burdens into a score in `[0,1]`
4. Assign a risk band for routing and triage

The score is intentionally designed to be compact, measurable, and actionable for agentic workflows.

---

## Metric Inventory

HotspotTriage computes these primary metrics (file and/or block, depending on granularity):

- `sloc`: source lines of code (comments/blank lines excluded)
- `cyclomatic`: McCabe complexity sum
- `halstead`: Halstead volume
- `maintainability`: `100 - MI` (higher is worse)
- `churn`: git additions + deletions
- `churn_per_sloc`: `churn / sloc`
- `decayed_churn`: churn exponentially decayed by block or file age
- `decayed_churn_per_sloc`: `decayed_churn / sloc`
- `smell_count`: number of smell findings
- `smell_severity`: average per-finding severity in `[0,1]`
- `smell_burden`: blended smell measure (see section 4)
- `similarity_score`: DeepCSIM best match score in `[0,100]`
- `match_count`: similar peer count over threshold

Some metrics are base metrics, while others are derived for normalization or aggregation.

---

## Where the numbers come from

The scoring stack starts with **Radon**. Radon gives us structural code signals (`sloc`, `cyclomatic`, `halstead`, and MI), and HotspotTriage converts MI to a risk-oriented scale (`maintainability = 100 - MI`) so "higher means worse" stays consistent.

Then we layer in **Git history**. File-level churn comes from `git log`, and block-level churn comes from `git log -L` so each function/method can carry its own change pressure. From there we derive `churn_per_sloc`, `decayed_churn`, and `decayed_churn_per_sloc` inside HotspotTriage.

For smells, we use a mixed pipeline in `hotspottriage.smell`: selected **Pylint** findings, a few project heuristics built on top of those findings, and comment-based checks built with Radon raw stats plus Python's `tokenize`. That produces `smell_count`, per-finding severities (averaged into `smell_severity`), and finally `smell_burden`.

For duplication pressure in block mode, we use **DeepCSIM** (`deepcsim`) to compute `similarity_score`, `match_count`, and `similarity_band`.

Finally, score composition is fully internal:

- file mode: product score in `hotspottriage.stats._score`
- block mode: normalized weighted aggregation in `hotspottriage.score.compute_score`, applied from `hotspottriage.stats`

So in plain terms: **Radon gives structure, Git gives volatility, Pylint/heuristics give quality smells, DeepCSIM gives similarity pressure, and HotspotTriage merges all of it into the final score.**

---

## 3) Metric Origins in Python Tooling

Each metric comes from a specific analysis layer or Python tooling family.

### `cyclomatic`

**Radon** computes cyclomatic complexity from Python AST analysis.

At block level, this reflects control-flow complexity in the analyzed region.

Interpretation:

- higher values mean more branching and decision paths
- it is one of the most direct “how hard is this logic?” signals

### `halstead`

**Radon** also provides Halstead metrics.

Halstead volume approximates implementation complexity based on operators and operands rather than branching alone.

Interpretation:

- captures a different dimension than cyclomatic complexity
- helps identify code that is cognitively dense even when branching is moderate

### `sloc`

**Radon** raw metrics provide the source-size basis for `sloc`.

Interpretation:

- larger units may deserve more review attention
- but size alone is not treated as sufficient evidence of risk

### `maintainability`

**Radon** provides Maintainability Index (MI), which HotspotTriage inverts as:

`maintainability = 100 - MI`

This inversion preserves a single scoring convention: higher values mean worse risk.

### `churn`

Derived from **git history**, not from Radon.

Typical implementation is:

- additions + deletions
- accumulated over a configured time horizon or revision history

Interpretation:

- frequently modified code tends to be less stable
- high churn may indicate design pressure, unclear ownership, or ongoing refactoring

### `churn_per_sloc`

Derived metric:

`churn_per_sloc = churn / sloc`

Interpretation:

- normalizes churn by size
- prevents large blocks from dominating purely because they are large
- surfaces smaller blocks that are disproportionately volatile

### `decayed_churn`

Churn adjusted by exponential decay so recent activity matters more than old history.

Interpretation:

- recent instability is usually more actionable than distant instability
- this makes the score more responsive to the current state of the codebase

### `decayed_churn_per_sloc`

Derived metric:

`decayed_churn_per_sloc = decayed_churn / sloc`

This is often the strongest hotspot signal because it combines:

- recency
- change pressure
- size normalization

### `smell_count`, `smell_severity`, `smell_burden`

These come from HotspotTriage's smell-detection pipeline in `src/hotspottriage/smell.py`.

Current implementation combines three sources:

- selected **Pylint** rules (normalized into smell IDs)
- **approximate heuristic smells** derived from Pylint signals
- **comment-density/comment-block** smells from Radon raw + tokenization

Interpretation:

- they enrich hotspot scoring with structural quality signals
- they help distinguish merely active code from problematic active code

#### Smells currently considered

The following smell IDs are currently emitted and counted:

- `long_method`
- `large_class`
- `long_parameter_list`
- `switch_statements`
- `lazy_class`
- `unused_parameters`
- `dead_code`
- `data_class` (approximate)
- `middle_man` (approximate)
- `speculative_generality` (approximate)
- `excessive_comments`
- `large_comment_block`

#### Pylint-backed mapping

HotspotTriage enables a specific Pylint message-id subset and maps them to smell IDs:

- `R0915` (`too-many-statements`) -> `long_method`
- `R0902` (`too-many-instance-attributes`) -> `large_class`
- `R0904` (`too-many-public-methods`) -> `large_class`
- `R0913` (`too-many-arguments`) -> `long_parameter_list`
- `R0912` (`too-many-branches`) -> `switch_statements`
- `R0903` (`too-few-public-methods`) -> `lazy_class`
- `W0613` (`unused-argument`) -> `unused_parameters`
- `W0611` (`unused-import`) -> `dead_code`
- `W0612` (`unused-variable`) -> `dead_code`

#### Approximate heuristic smells

These are intentionally marked approximate in findings:

- `data_class`:
  - triggered when a class is both `R0902` (many attributes) and `R0903` (few public methods)
  - attribute threshold: `smell_data_class_min_attributes` (default 8)
- `middle_man`:
  - triggered for classes with few public methods and very small mean method SLOC
  - threshold: `smell_middle_man_max_avg_method_sloc` (default 2.0)
- `speculative_generality`:
  - triggered when both unused imports and unused variables hit configured minimum counts
  - threshold: `smell_speculative_generality_min_hits` (default 1)

#### Comment smells

Two smells are computed from source text:

- `excessive_comments`:
  - when `comments / sloc` exceeds `smell_max_comment_ratio` (default 0.5)
- `large_comment_block`:
  - when max consecutive comment-token lines exceed `smell_max_comment_block_lines` (default 15)

#### Severity assignment (`smell_severity`)

Each finding gets a severity in `[0,1]` via this precedence:

1. exact smell ID in `smell_rule_weights`
2. fallback by Pylint category letter in `smell_category_weights` (`F`, `E`, `W`, `R`, `C`)
3. fallback default `smell_default_weight` (default `0.4`)

For each file/block, `smell_severity` is the average of finding severities.

### `similarity_score`

This metric comes from clone or similarity analysis, such as DeepCSIM-backed workflows.

Interpretation:

- repeated or highly similar code may indicate duplication burden
- similarity is naturally bounded in `[0,100]`, which makes it straightforward to normalize

---

## 4) Smell Burden Derivation

Before aggregation, `smell_burden` is computed from two pieces:

1. Run-local normalized count:
   - `norm_smell_count = smell_count / max(1, max_smell_count_in_this_run)`
2. Average smell severity:
   - `smell_severity` already in `[0,1]`

Then:

`smell_burden = 0.5 * norm_smell_count + 0.5 * smell_severity`

This means smell burden is comparable inside a single analysis batch and remains in `[0,1]`.

Why this design works:

- count captures how many smell findings exist
- severity captures how serious those findings are
- averaging the two prevents either frequency or seriousness from dominating completely

---

## 5) Decayed Churn

Decayed churn uses exponential half-life:

`decayed = raw_value * 0.5 ^ (age_seconds / half_life_seconds)`

Default half-life:

`decay_half_life = 2,592,000` seconds (30 days)

Notes:

- If half-life is disabled (`null`), decayed values equal raw churn values.
- If age is 0 or negative, value is left unchanged.

Practical meaning:

- very recent edits retain most of their weight
- older edits fade smoothly rather than disappearing abruptly
- the half-life controls how quickly historical heat cools down

---

## 6) Aggregated 0-1 Risk Score

When `score_aggregation.enabled: true` (default), HotspotTriage computes a weighted aggregated risk score in `[0,1]`.

Final outputs:

- `score` in `[0,1]`
- `score_band` (`low`, `medium`, `high`, `critical` by default)
- `score_subscores` dictionary with burden components

### 6.1 Subscores ("burdens")

The final score is built from five burdens:

- `complexity_burden`
- `churn_burden`
- `maintainability_burden`
- `smell_burden`
- `similarity_burden` (if similarity is available)

Each burden is a weighted combination of normalized inputs.

### 6.2 Why aggregation exists

The aggregated path exists because raw metrics live on very different scales.

Without normalization and explicit weighting:

- large-range metrics could dominate unfairly
- extreme values would be harder to interpret
- thresholds would be unstable
- dashboards would be less meaningful

By normalizing first and aggregating second, HotspotTriage produces a score that is easier to explain and safer to use operationally.

Clipping is applied to keep normalized values and the final score within bounded ranges, which makes the result threshold-friendly and suitable for dashboard interpretation.

---

## 7) Risk Bands

For aggregated scoring, default band thresholds are:

```yaml
band_edges: [0.30, 0.60, 0.80]
band_names: [low, medium, high, critical]
```

Classification:

- `< 0.30` -> `low`
- `0.30` to `< 0.60` -> `medium`
- `0.60` to `< 0.80` -> `high`
- `>= 0.80` -> `critical`

These bands are especially useful for:

- dashboards
- triage queues
- review prioritization
- alerting and policy discussions

---

## 8) Similarity Availability Rules

Similarity burden only participates when similarity data is available:

- typically with `similarity_enabled: true`
- when unavailable, `similarity_burden` is removed from final weighting
- remaining final weights are proportionally renormalized

This avoids penalizing runs where similarity is intentionally disabled or not computed.

---

## 9) Score narratives

Block rows with risk aggregation add `score_driver`, `score_explanation` (ranked burdens with raw metrics), and a multi-line `score_narrative` from `hotspottriage.explain` so CLI, MCP `analyze`, and the API reuse the same phrasing. Rankings and copy include **`final_weight × burden`** (score contribution) when aggregation is on, so the narrative matches how the composite `score` is built. Detail lines use the same **normalized** metric inputs as `compute_score` (prefixed `n_<metric>=…`), not raw counters, for driver context. The dashboard heatmap loads that narrative on demand via `GET /api/stats/block_narrative?path=…` instead of embedding it in every row payload; heatmap matrix cells remain raw burdens plus composite `score`.