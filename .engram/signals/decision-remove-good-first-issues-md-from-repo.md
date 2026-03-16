---
type: decision
date: 2026-03-16
tags: [cleanup, repo]
links: [related:decision-add-ci-workflow-security-policy-funding-faq-and-go]
source: git:a7189145e0dbacb434058fe8be4b9b7bb1d4c47e
---

# Remove good-first-issues.md from repo

Reference file for issue creation, not meant to be tracked.

 good-first-issues.md | 96 ----------------------------------------------------
 1 file changed, 96 deletions(-)

## Rationale

Temporary reference file — only needed to seed GitHub issues, not meant to live in the repo.

## Alternatives

Keep in `.github/` — but it's not a GitHub template or config file, just a one-time reference.
