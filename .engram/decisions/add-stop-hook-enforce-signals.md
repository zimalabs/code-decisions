+++
date = 2026-03-16
tags = ["hooks", "enforcement", "dogfooding"]
links = ["related:pre-commit-gate-hook"]
+++

Add prompt-based Stop hook that blocks the agent from finishing if significant code changes were made without writing a decision signal. Enforces the "write before committing" rule systemically instead of relying on memory.

## Rationale

Agents forget to write decision signals even when CLAUDE.md explicitly tells them to. Under time pressure or complex tasks, signal writing gets deprioritized. A systemic enforcement at session end catches the gap before context is lost.

## Alternatives

- Rely on CLAUDE.md instructions alone — insufficient, agents skip under pressure
- Pre-commit gate only — added later as a second enforcement layer; Stop hook was the first
