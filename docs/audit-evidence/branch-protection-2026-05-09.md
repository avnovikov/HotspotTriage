# Branch Protection — `main` — 2026-05-09

Audit evidence for issue [#90](https://github.com/avnovikov/HotspotTriage/issues/90)
("Configure branch protection + required status checks on `main`").

## SOC 2 mapping

| Control | Criteria                                       |
| ------- | ---------------------------------------------- |
| CC8.1   | Authorizes changes before implementation       |
| CC6.6   | Restricts access to production environment     |

## Mechanism

GitHub **Repository Ruleset** (modern equivalent of classic branch protection)
applied to the default branch (`~DEFAULT_BRANCH`, currently `main`) on
`avnovikov/HotspotTriage`.

- Ruleset id: `15966604`
- Ruleset name: `protect main branch`
- Enforcement: **active** (applies to everyone, including admins)
- Settings UI: <https://github.com/avnovikov/HotspotTriage/rules/15966604>
- API export: [`branch-protection-2026-05-09.json`](./branch-protection-2026-05-09.json)
- Effective rules on `main`: [`branch-protection-effective-main-2026-05-09.json`](./branch-protection-effective-main-2026-05-09.json)

## Active rules on `main`

| Rule                          | Setting                                                                 | Acceptance criterion satisfied                              |
| ----------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------- |
| `pull_request`                | 1 approving review required, dismiss stale reviews on push, require code-owner review, all merge methods allowed | Require PR before merging; require 1 approving review; dismiss stale reviews on new commits |
| `required_status_checks`      | strict (branch must be up to date), checks: `SAST + Dependencies + Secrets`, `Security Gate (PR only)` | Require status checks `Security & Compliance Scans`; require branches to be up to date before merging |
| `non_fast_forward`            | enabled                                                                 | Block force-push that rewrites history                      |
| `deletion`                    | enabled                                                                 | Block deletion of `main`                                    |
| `required_linear_history`     | enabled                                                                 | No merge commits that obscure provenance                    |

Combined with the absence of any push-allowance rule, **direct pushes to `main`
are blocked**. The only ingress to `main` is via a PR that has (a) at least one
approving review, (b) the two required security checks passing, and (c) the
branch up to date with `main`.

## Bypass actors

| Actor                          | Mode      | Rationale                                                                                                                                       |
| ------------------------------ | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Repository role: **Admin** (id `5`) | `always` | Sole-maintainer escape hatch. GitHub does not allow self-approval, so without this bypass the owner cannot merge their own PRs. The bypass is logged in the GitHub audit log per merge — auditor-visible. |

This is the only bypass actor. AI agents (Cursor, etc.) authenticate with the
owner's `gh` token and therefore inherit the same bypass capability **on
GitHub's side** — that capability is restricted on the **agent side** by the
local Cursor skill `no-pr-merge-without-explicit-ok` (typically under `~/.cursor/skills/` on the workstation; not vendored in this repository):
agents may open PRs but must not merge or close issues by merging without
explicit per-conversation permission from the user.

## Manual screenshot (auditor-friendly)

Per the issue's acceptance criteria, save a PNG of the GitHub UI showing the
ruleset to:

```
docs/audit-evidence/branch-protection-2026-05-09.png
```

Open <https://github.com/avnovikov/HotspotTriage/rules/15966604>, expand all
rule sections, and capture the page. The JSON exports above are the source of
truth; the screenshot is a human-readable companion for auditors.

## Future enhancements (not blocking #90)

- **`required_signatures`**: enable once SSH or GPG commit signing is set up
  locally. The previous (disabled) ruleset already had this; it was dropped
  from the active set because every commit currently on `main` is unsigned and
  enabling it would lock out merges. Tracked separately.
- **CODEOWNERS**: `require_code_owner_review` is on but `CODEOWNERS` does not
  yet exist. Issue [#91](https://github.com/avnovikov/HotspotTriage/issues/91)
  adds it; once present, code-owner approval will be enforced as the issue
  intends.
