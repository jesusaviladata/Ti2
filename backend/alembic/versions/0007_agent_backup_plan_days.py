"""Add configurable weekdays to agent backup plans.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS also repairs environments that briefly ran a 0005 file
    # containing these columns before the forward-only migration was added.
    op.execute(
        """
        ALTER TABLE agent_backup_plans
        ADD COLUMN IF NOT EXISTS "full_days" JSONB NOT NULL DEFAULT '[0, 2, 4]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE agent_backup_plans
        ADD COLUMN IF NOT EXISTS "differential_days" JSONB NOT NULL DEFAULT '[1, 3]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE agent_backup_plans DROP COLUMN IF EXISTS "differential_days"'
    )
    op.execute('ALTER TABLE agent_backup_plans DROP COLUMN IF EXISTS "full_days"')
