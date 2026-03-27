---
name: "capture-nudge-corroboration-requirement"
description: "Capture-nudge requires trigger phrase + technical signal (or 2+ phrases) to reduce false positives"
date: "2026-03-20"
tags:
  - "hooks"
  - "capture-nudge"
  - "ux"
affects:
  - "src/decision/policy/capture_nudge.py"
---

# Capture-nudge requires corroborating evidence before firing

The capture-nudge hook now requires either a trigger phrase paired with a technical signal (inline code, snake_case, file path, etc.) or two or more distinct trigger phrases in the same message. Single casual phrases like "let's go with" in non-technical conversation no longer fire the nudge.

## Alternatives
- **Single-phrase trigger (status quo)**: Any one decision phrase fires the nudge. Simple but produced false positives on casual conversation — users saying "let's go with lunch" would get nudged to capture a decision.
- **Require 2+ phrases only**: Would miss legitimate single-phrase decisions that clearly reference code (`"let's go with redis_cache instead"`). Too strict for technical messages.
- **Phrase + technical signal OR 2+ phrases (chosen)**: Balances sensitivity — technical context is a strong signal even with one phrase, and multiple decision phrases indicate genuine deliberation even without code references.

## Rationale
The `_DECISION_PHRASE` regex in `src/decision/policy/capture_nudge.py` matches common decision language, but these phrases appear in everyday conversation too. Adding `_TECHNICAL_SIGNAL` (inline code backticks, snake_case identifiers, CamelCase, dotted paths, file paths) as a corroborating requirement filters out casual conversation while preserving detection of real technical decisions. The OR with 2+ phrases catches cases where someone is clearly deliberating ("we decided... after weighing the trade-off") even without code references.

## Trade-offs
- **False negatives increase**: A user saying "let's go with option A" without any code reference will not be nudged. This is acceptable because purely conversational decisions without technical specificity are unlikely to produce useful decision records anyway.
- **Regex coupling**: The `_TECHNICAL_SIGNAL` pattern is tuned for Python/general programming conventions. Languages with different naming conventions (e.g., kebab-case in Clojure) may not be detected. Reversible by expanding the regex.
