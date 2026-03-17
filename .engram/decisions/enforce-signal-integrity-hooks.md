---
type: decision
date: 2026-03-17
tags: [hooks, enforcement]
links: [related:pre-commit-gate-hook]
---

# Add enforcement hooks for signal integrity, subagent context, and post-push resync

Four enforcement gaps closed: (1) pre-delete-guard blocks rm/git-checkout/git-restore on .engram/ signal files, protecting append-only rule; (2) pre-tool-use edit guard blocks Edit with empty new_string on signal files, preventing content deletion; (3) subagent-stop now injects brief.md so subagents have decision context; (4) post-push-resync auto-resyncs after git push.

## Rationale

Advisory hooks (nudges, systemMessages) don't change agent behavior — agents ignore them. Blocking hooks via PreToolUse `decision: block` are the only reliable enforcement mechanism. Subagents were completely blind to past decisions because they don't receive SessionStart context injection.

## Alternatives

- **Advisory-only approach** — already proven insufficient, agents skip capture and sometimes delete signals.
- **Git pre-commit hooks** — only work with git tracking enabled, don't integrate with Claude's tool permission system, and can't block Edit/Write tool calls.
