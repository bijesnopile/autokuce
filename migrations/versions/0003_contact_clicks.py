"""contact_clicks: daily WhatsApp/Viber click counts (phase 9, package Standard)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_contact_clicks_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_clicks")),
    )
    with op.batch_alter_table("contact_clicks") as batch_op:
        batch_op.create_index(batch_op.f("ix_contact_clicks_date"), ["date"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_contact_clicks_vehicle_id"), ["vehicle_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("contact_clicks") as batch_op:
        batch_op.drop_index(batch_op.f("ix_contact_clicks_vehicle_id"))
        batch_op.drop_index(batch_op.f("ix_contact_clicks_date"))
    op.drop_table("contact_clicks")
