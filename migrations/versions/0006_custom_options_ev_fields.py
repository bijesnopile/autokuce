"""custom_options (dealer-defined options) + electric vehicle fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29 20:00:00

Electric vehicles used to store kWh/100 km in fuel_consumption_l100 (form help text);
those values move to energy_consumption_kwh100.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=True),
        sa.Column("vehicle_type", sa.String(length=20), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_custom_options_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_options")),
        sa.UniqueConstraint("scope", "code", name="uq_custom_options_scope_code"),
    )
    with op.batch_alter_table("custom_options") as batch_op:
        batch_op.create_index(batch_op.f("ix_custom_options_scope"), ["scope"], unique=False)
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.add_column(sa.Column("energy_consumption_kwh100", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("electric_range_km", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("battery_kwh", sa.Float(), nullable=True))
    op.execute(
        "UPDATE vehicles SET energy_consumption_kwh100 = fuel_consumption_l100, "
        "fuel_consumption_l100 = NULL WHERE fuel = 'elektricni'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE vehicles SET fuel_consumption_l100 = energy_consumption_kwh100 "
        "WHERE fuel = 'elektricni'"
    )
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.drop_column("battery_kwh")
        batch_op.drop_column("electric_range_km")
        batch_op.drop_column("energy_consumption_kwh100")
    with op.batch_alter_table("custom_options") as batch_op:
        batch_op.drop_index(batch_op.f("ix_custom_options_scope"))
    op.drop_table("custom_options")
