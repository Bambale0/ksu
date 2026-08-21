"""allow video prompt tool tasks

Revision ID: 0018_prompt_tool_video
Revises: 0017_prompt_tools
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_prompt_tool_video"
down_revision: str | None = "0017_prompt_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_CHECK = "tool IN ('image_analysis', 'prompt_builder', 'video_prompt')"
OLD_CHECK = "tool IN ('image_analysis', 'prompt_builder')"


def upgrade() -> None:
    op.drop_constraint("ck_prompt_tool_tasks_tool", "prompt_tool_tasks", type_="check")
    op.create_check_constraint("ck_prompt_tool_tasks_tool", "prompt_tool_tasks", NEW_CHECK)


def downgrade() -> None:
    op.drop_constraint("ck_prompt_tool_tasks_tool", "prompt_tool_tasks", type_="check")
    op.create_check_constraint("ck_prompt_tool_tasks_tool", "prompt_tool_tasks", OLD_CHECK)
