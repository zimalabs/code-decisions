"""Policy definitions — registry of all policies."""

from ..utils.constants import WRITE_TOOLS
from ._helpers import (
    _CODE_NOISE as _CODE_NOISE,
)
from ._helpers import (
    _extract_content_keywords as _extract_content_keywords,
)
from ._helpers import (
    _extract_file_path as _extract_file_path,
)
from ._helpers import (
    _is_decision_path as _is_decision_path,
)
from .capture_nudge import _capture_nudge_condition
from .content_validation import _content_validation_condition
from .edit_checkpoint import _edit_checkpoint_condition
from .edit_validation import _edit_validation_condition
from .engine import Policy, PolicyLevel
from .impl_nudge import _impl_nudge_condition
from .index_update import _index_update_condition
from .plan_nudge import _plan_nudge_condition
from .query_preseed import _query_preseed_condition
from .related_context import _related_context_condition
from .session_context import _session_context_condition
from .session_init import _session_init_condition
from .stop_nudge import _stop_nudge_condition

# Policies are evaluated in registration order, grouped by PolicyLevel.
# The engine sorts by level (BLOCK → LIFECYCLE → CONTEXT → NUDGE) and
# evaluates within each level in the order listed here.
#
# Ordering rationale:
#   BLOCK:     content/edit validation — structural checks on Write/Edit
#   LIFECYCLE: session-init runs alone (sets up store before anything else)
#   CONTEXT:   session-context before related-context — session-wide summary first,
#              then file-specific context
#   NUDGE:     capture nudge on UserPromptSubmit before edit-checkpoint on
#              PostToolUse (user prompt comes first temporally); stop-nudge is
#              once_per_session and runs at Stop
ALL_POLICIES: list[Policy] = [
    # BLOCK
    Policy(
        name="content-validation",
        description="Validate decision file structure and quality on Write",
        level=PolicyLevel.BLOCK,
        events=["PreToolUse"],
        matchers=["Write"],
        condition=_content_validation_condition,
    ),
    Policy(
        name="edit-validation",
        description="Warn if Edit/MultiEdit corrupts a decision file",
        level=PolicyLevel.BLOCK,
        events=["PostToolUse"],
        matchers=["Edit", "MultiEdit"],
        condition=_edit_validation_condition,
    ),
    # LIFECYCLE
    Policy(
        name="session-init",
        description="Initialize decision store, print banner",
        level=PolicyLevel.LIFECYCLE,
        events=["SessionStart"],
        matchers=["*"],
        condition=_session_init_condition,
    ),
    # CONTEXT
    Policy(
        name="session-context",
        description="Inject decision summary and instructions at session start",
        level=PolicyLevel.CONTEXT,
        events=["SessionStart"],
        matchers=["*"],
        condition=_session_context_condition,
    ),
    Policy(
        name="related-context",
        description="Inject related past decisions when editing code files",
        level=PolicyLevel.CONTEXT,
        events=["PostToolUse"],
        matchers=sorted(WRITE_TOOLS),
        condition=_related_context_condition,
    ),
    Policy(
        name="index-update",
        description="Auto-regenerate .claude/rules/decisions.md after decision writes",
        level=PolicyLevel.CONTEXT,
        events=["PostToolUse"],
        matchers=["Write"],
        condition=_index_update_condition,
    ),
    # NUDGE
    Policy(
        name="capture-nudge",
        description="Detect decision language in user messages, suggest capture",
        level=PolicyLevel.NUDGE,
        events=["UserPromptSubmit"],
        matchers=["*"],
        condition=_capture_nudge_condition,
    ),
    Policy(
        name="query-preseed",
        description="Pre-seed Python query results when /decision is invoked with search intent",
        level=PolicyLevel.NUDGE,
        events=["UserPromptSubmit"],
        matchers=["*"],
        condition=_query_preseed_condition,
    ),
    # CHECKPOINT
    Policy(
        name="edit-checkpoint",
        description="Nudge decision capture every N code edits mid-session",
        level=PolicyLevel.NUDGE,
        events=["PostToolUse"],
        matchers=sorted(WRITE_TOOLS),
        condition=_edit_checkpoint_condition,
    ),
    Policy(
        name="impl-nudge",
        description="Detect implementation decisions from agent behavior (new files, structural changes)",
        level=PolicyLevel.NUDGE,
        events=["PostToolUse"],
        matchers=sorted(WRITE_TOOLS),
        condition=_impl_nudge_condition,
    ),
    Policy(
        name="plan-nudge",
        description="Extract decision candidates from Claude Code plan files and nudge at implementation start",
        level=PolicyLevel.NUDGE,
        events=["PostToolUse"],
        matchers=sorted(WRITE_TOOLS),
        condition=_plan_nudge_condition,
    ),
    Policy(
        name="stop-nudge",
        description="Nudge agent to capture decisions before ending a session with significant edits",
        level=PolicyLevel.NUDGE,
        events=["Stop"],
        matchers=["*"],
        condition=_stop_nudge_condition,
        once_per_session=True,
    ),
]
