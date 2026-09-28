"""euro_norm: VARCHAR(10) -> VARCHAR(20) ("euro6d_temp" has 11 characters)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28 21:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.alter_column(
            "euro_norm",
            existing_type=sa.String(length=10),
            type_=sa.String(length=20),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.alter_column(
            "euro_norm",
            existing_type=sa.String(length=20),
            type_=sa.String(length=10),
            existing_nullable=True,
        )
