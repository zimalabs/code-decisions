---
type: decision
date: 2026-03-17
tags: [architecture, hooks, policy-engine]
---

# Formalize engram policy layer

Replaced 12 independent shell hook scripts with a centralized Python policy engine. Every hook is now a thin shell dispatcher (`dispatch.sh <event>`) that pipes stdin to `python3 -m engram policy <event>`, which evaluates all registered policies for that event.

## Rationale

The 13 hooks evolved organically — each was an independent shell script with its own boilerplate, JSON parsing, state management, and response formatting. This made it hard to add new policies, introspect active enforcement, and maintain consistent behavior. The policy engine centralizes all enforcement logic into Python dataclasses with structured evaluation: BLOCK (fail-fast) → LIFECYCLE → CONTEXT → NUDGE.

## Alternatives

- Keep shell scripts with shared library — rejected because the shared logic (JSON parsing, state management, response formatting) is better expressed in Python, and the shell→Python boundary adds fragility.
- Declarative YAML policy definitions — rejected because conditions inspect command strings, file paths, and content in ways that can't be expressed without code.

## What changed

- Created `policy.py` (engine framework: PolicyEngine, Policy, PolicyLevel, PolicyResult, SessionState)
- Created `_policy_defs.py` (15 policies ported from 12 shell scripts)
- Created `dispatch.sh` (8-line universal dispatcher)
- Created `test_policy.py` (52 tests for engine + all policies)
- Created `skills/policies/SKILL.md` (introspection via `python3 -m engram policy`)
- Deleted 12 old hook scripts, repointed `hooks.json` to dispatch.sh
- Updated existing tests to use dispatch.sh
- SessionState unified from 5 scattered `/tmp/engram-*` patterns to single directory
