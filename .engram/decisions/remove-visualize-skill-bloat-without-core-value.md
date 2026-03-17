+++
date = 2026-03-16
tags = ["cleanup", "skill"]
links = ["supersedes:add-visualize-skill"]
source = "git:d882f36151be9e7f2a6413ee89c3c74bc819632f"
+++

# Remove visualize skill — bloat without core value

350-line HTML template in SKILL.md added maintenance burden. Removes
skill directory, visualize.html gitignore entries, and related test
assertions.

.engram/.gitignore                       |   1 -
 README.md                                | 109 ++--------
 plugins/engram/lib.sh                    |  45 +---
 plugins/engram/skills/visualize/SKILL.md | 342 -------------------------------
 plugins/engram/tests/test_engram.sh      | 154 ++------------
 5 files changed, 40 insertions(+), 611 deletions(-)

## Rationale

The 350-line HTML template in SKILL.md added maintenance burden without proven value. Visualization isn't core to decision memory — it's better served by external tools if needed.

## Alternatives

- Keep but simplify — still overhead for a feature nobody used
- Move to separate optional plugin — over-engineering for unvalidated demand
