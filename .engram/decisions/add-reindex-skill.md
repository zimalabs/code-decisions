---
type: decision
date: 2026-03-16
tags: [skill, reindex, dx]
---

# Add @engram:reindex skill for on-demand index rebuilds

Users who manually edit or add signal files mid-session had no way to refresh `index.db` until the next session boundary. Added a skill that runs the full pipeline on demand.

## Alternatives
- Run the bash pipeline manually — requires knowing function names and sourcing lib.sh; error-prone.
- Add a hook on file write — too noisy, would fire on every Write tool call, not just signal edits.

## Rationale
A skill is the lightest-weight option: no new code in lib.sh, just a SKILL.md that shells out to the existing pipeline (`ingest_commits → ingest_plans → reindex → brief`). Reports signal counts after completion for confirmation.
