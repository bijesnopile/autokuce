"""feed_access: last download per portal feed (phase 9, package Standard)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feed_access",
        sa.Column("portal", sa.String(length=30), nullable=False),
        sa.Column("last_at", sa.DateTime(), nullable=False),
        sa.Column("last_format", sa.String(length=4), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("portal", name=op.f("pk_feed_access")),
    )


def downgrade() -> None:
    op.drop_table("feed_access")
