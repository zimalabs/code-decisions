---
type: decision
date: 2026-03-16
source: git:168b6a3eef1ee4dbf69bdecbdb1bcee8e66c4589
---

# Add CI workflow, security policy, funding, FAQ, and good-first-issues

Prepares repo for public launch:
- GitHub Actions CI (ubuntu + macOS matrix, shellcheck + tests)
- CI badge in README
- FAQ section answering common questions (CLAUDE.md comparison, privacy, portability)
- SECURITY.md with vulnerability reporting process
- FUNDING.yml enabling GitHub Sponsors
- Good-first-issue descriptions for community contributors
- Updated README comparison table and copy

 .github/FUNDING.yml      |  1 +
 .github/SECURITY.md      | 30 +++++++++++++++
 .github/workflows/ci.yml | 28 ++++++++++++++
 README.md                | 60 ++++++++++++++++++++++++------
 good-first-issues.md     | 96 ++++++++++++++++++++++++++++++++++++++++++++++++
 5 files changed, 204 insertions(+), 11 deletions(-)
