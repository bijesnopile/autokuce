"""vehicle_price_history: price changes (discount badge, public drops, admin history)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-29 22:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_price_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("old_price", sa.Integer(), nullable=True),
        sa.Column("new_price", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_vehicle_price_history_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_vehicle_price_history_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicle_price_history")),
    )
    with op.batch_alter_table("vehicle_price_history") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_vehicle_price_history_changed_at"), ["changed_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_vehicle_price_history_vehicle_id"), ["vehicle_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("vehicle_price_history") as batch_op:
        batch_op.drop_index(batch_op.f("ix_vehicle_price_history_vehicle_id"))
        batch_op.drop_index(batch_op.f("ix_vehicle_price_history_changed_at"))
    op.drop_table("vehicle_price_history")
