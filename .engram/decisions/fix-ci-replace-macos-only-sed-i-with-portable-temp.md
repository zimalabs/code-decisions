+++
date = 2026-03-16
tags = ["ci", "macos"]
links = ["related:fix-ci-install-homebrew-sqlite-with-fts5-on-macos"]
source = "git:00bc106a2787a4d65345c842a330cc5d95f56e1b"
+++

# Fix CI: replace macOS-only sed -i '' with portable temp file pattern

plugins/engram/lib.sh | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

## Rationale

macOS `sed -i ''` syntax doesn't work on Linux CI runners. Replacing with a portable temp file pattern ensures CI works across platforms.

## Alternatives

- Use GNU sed syntax with `--in-place` — still platform-specific
- Conditional logic per OS — unnecessary complexity for a one-liner
