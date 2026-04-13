"""Seed decisions for the Superpowers plugin (obra/superpowers).

Each decision captures a methodology choice that Superpowers enforces —
design-first, TDD, systematic debugging, etc. These get written to
.claude/decisions/ so the team's adoption of the methodology is explicit,
searchable, and surfaces in related-context when editing affected files.
"""

from __future__ import annotations

from . import SeedDecision

_PREFIX = "superpowers"


def superpowers_seeds() -> list[SeedDecision]:
    """Return seed decisions representing the Superpowers methodology."""
    return [
        SeedDecision(
            slug=f"{_PREFIX}-design-first",
            name=f"{_PREFIX}-design-first",
            description="Always brainstorm and validate design before writing any code",
            tags=[_PREFIX, "workflow"],
            affects=["src/", "docs/"],
            title="Design before implementation",
            body=(
                "No code touches disk until the design is written and approved, "
                "because unexamined assumptions are the most expensive kind of rework. "
                "Even tasks that seem simple get a written design — those are highest-risk "
                "for hidden complexity.\n\n"
                "The workflow: explore context, ask clarifying questions, propose 2-3 approaches "
                "with trade-offs, write a spec to docs/superpowers/specs/, and get explicit "
                "approval before any implementation skill can run."
            ),
        ),
        SeedDecision(
            slug=f"{_PREFIX}-tdd",
            name=f"{_PREFIX}-tdd",
            description="No production code without a failing test first (RED-GREEN-REFACTOR)",
            tags=[_PREFIX, "testing"],
            affects=["src/", "tests/"],
            title="Test-driven development (RED-GREEN-REFACTOR)",
            body=(
                "Tests written after implementation prove nothing — they're biased by the code "
                "that already exists. Instead of verifying behavior, they verify implementation. "
                "The RED-GREEN-REFACTOR cycle chosen here catches edge cases during design rather "
                "than in production.\n\n"
                "The rule: write one minimal failing test (RED), watch it fail to prove it tests "
                "the right thing, write the simplest code to pass (GREEN), then clean up (REFACTOR). "
                "Code written before tests must be deleted and restarted. No exceptions for "
                "'simple' code — simple code breaks, and the test takes 30 seconds to write."
            ),
        ),
        SeedDecision(
            slug=f"{_PREFIX}-detailed-plans",
            name=f"{_PREFIX}-detailed-plans",
            description="Implementation plans must be complete with zero placeholders",
            tags=[_PREFIX, "workflow"],
            affects=["src/", "docs/"],
            title="Implementation plans with zero placeholders",
            body=(
                "Placeholders like TBD, TODO, and 'similar to Task N' delay the discovery of "
                "ambiguity until coding, when it's most expensive to resolve. Plans are written "
                "instead for an engineer with no codebase context, because that's effectively what "
                "a subagent is.\n\n"
                "Each task is 2-5 minutes of work with exact file paths, complete code, and "
                "verification steps. RED, verify RED, GREEN, verify GREEN, and COMMIT are "
                "separate steps. This granularity prevents multi-hour rabbit holes and makes "
                "progress observable."
            ),
        ),
        SeedDecision(
            slug=f"{_PREFIX}-subagent-development",
            name=f"{_PREFIX}-subagent-development",
            description="Fresh subagent per task with two-stage review (spec then quality)",
            tags=[_PREFIX, "workflow"],
            affects=["src/", "tests/"],
            title="Subagent-driven development with two-stage review",
            body=(
                "A fresh subagent per task prevents context pollution — accumulated state from "
                "earlier tasks biases later decisions. Instead of one long session that drifts, "
                "each task gets clean context with the full task specification.\n\n"
                "Review is two-stage in strict order: spec compliance first (does it match the "
                "spec — no more, no less?), then code quality (is it well-written?). This order "
                "matters because polishing wrong code is pure waste. Critical issues from review "
                "block progress."
            ),
        ),
        SeedDecision(
            slug=f"{_PREFIX}-systematic-debugging",
            name=f"{_PREFIX}-systematic-debugging",
            description="Root cause investigation before any fixes — no random changes",
            tags=[_PREFIX, "debugging"],
            affects=["src/", "tests/"],
            title="Root cause investigation before fixes",
            body=(
                "Random fixes waste time and create new bugs. The alternative chosen here is "
                "systematic debugging: read error messages completely, reproduce consistently, "
                "check recent changes, trace data flow backward to find where the bad value "
                "originates.\n\n"
                "Fixes require a stated hypothesis ('X causes Y because Z') tested one variable "
                "at a time. If 3+ fixes have failed, stop — the pattern indicates an architectural "
                "problem, not a coding problem. Discuss refactoring instead of attempting another "
                "patch."
            ),
        ),
        SeedDecision(
            slug=f"{_PREFIX}-git-worktrees",
            name=f"{_PREFIX}-git-worktrees",
            description="Use git worktrees for feature branch isolation with verified baselines",
            tags=[_PREFIX, "git"],
            affects=["src/", "tests/"],
            title="Git worktrees for feature isolation",
            body=(
                "Git worktrees provide true filesystem isolation for feature branches instead of "
                "stashing or switching branches in-place, which risks contaminating the working "
                "directory. This was chosen over simple branching because subagent-driven development "
                "benefits from a clean, independent working copy.\n\n"
                "The worktree directory must be gitignored (verified before creation). After checkout, "
                "project setup runs automatically and tests are verified to pass at baseline. A failing "
                "baseline is a hard stop — you can't distinguish new bugs from pre-existing ones."
            ),
        ),
        SeedDecision(
            slug=f"{_PREFIX}-verify-before-complete",
            name=f"{_PREFIX}-verify-before-complete",
            description="No completion claims without fresh verification evidence",
            tags=[_PREFIX, "quality"],
            affects=["src/", "tests/"],
            title="Verification evidence before completion claims",
            body=(
                "Confidence is subjective, evidence is objective. Claiming 'tests pass' without "
                "running the test suite, or 'build succeeds' without checking the exit code, is "
                "not verification — it's guessing. This rule exists because unverified claims erode "
                "trust and hide real failures.\n\n"
                "Before any completion claim: identify the verification command, run it fresh, "
                "read the full output, and confirm the output matches the claim. Partial checks "
                "(linter passed but compiler not run) prove nothing. Words like 'should' and "
                "'probably' are red flags that evidence is missing."
            ),
        ),
        SeedDecision(
            slug=f"{_PREFIX}-spec-before-quality",
            name=f"{_PREFIX}-spec-before-quality",
            description="Review spec compliance before code quality — wrong code polished is waste",
            tags=[_PREFIX, "quality"],
            affects=["src/", "tests/"],
            title="Spec compliance review before code quality review",
            body=(
                "Code quality review before spec compliance review risks polishing the wrong "
                "implementation — optimizing code that doesn't match the spec is pure waste. "
                "By checking spec compliance first, wrong implementations are caught before any "
                "effort goes into making them elegant.\n\n"
                "The spec compliance check asks: does the code do exactly what was specified, "
                "no more, no less? Over-building is as much a spec violation as under-building. "
                "Only after spec compliance passes does code quality review begin."
            ),
        ),
    ]
