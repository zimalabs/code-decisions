"""Policy ordering guard — prevents accidental reordering that changes behavior.

ALL_POLICIES evaluation order matters within each level. This test locks the
ordering so changes are intentional and visible in diffs.
"""

from decision.policy.defs import ALL_POLICIES

# Locked ordering — update this list intentionally when adding/removing/reordering policies.
EXPECTED_POLICY_ORDER = [
    # BLOCK
    "content-validation",
    "edit-validation",
    # LIFECYCLE
    "session-init",
    # CONTEXT
    "session-context",
    "related-context",
    # NUDGE
    "capture-nudge",
    "query-preseed",
    "edit-checkpoint",
    "impl-nudge",
    "plan-nudge",
    "stop-nudge",
]


def test_policy_ordering_is_locked():
    """ALL_POLICIES order must match EXPECTED_POLICY_ORDER.

    If you intentionally reorder, add, or remove a policy, update
    EXPECTED_POLICY_ORDER in this file. This guard prevents accidental
    reordering which can change behavior (e.g., review-health must run
    before session-context at SessionStart).
    """
    actual = [p.name for p in ALL_POLICIES]
    assert actual == EXPECTED_POLICY_ORDER, (
        f"Policy ordering changed!\n"
        f"  Expected: {EXPECTED_POLICY_ORDER}\n"
        f"  Actual:   {actual}\n"
        f"If intentional, update EXPECTED_POLICY_ORDER in test_policy_ordering.py"
    )


def test_policy_count_matches():
    """Catch accidental additions or removals."""
    assert len(ALL_POLICIES) == len(EXPECTED_POLICY_ORDER), (
        f"Policy count mismatch: {len(ALL_POLICIES)} registered vs "
        f"{len(EXPECTED_POLICY_ORDER)} expected. Update EXPECTED_POLICY_ORDER."
    )
