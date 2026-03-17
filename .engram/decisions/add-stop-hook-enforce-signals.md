+++
date = 2026-03-16
tags = ["hooks", "enforcement", "dogfooding"]
+++

Add prompt-based Stop hook that blocks the agent from finishing if significant code changes were made without writing a decision signal. Enforces the "write before committing" rule systemically instead of relying on memory.
