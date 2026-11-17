"""Add finance_watchlists table and list_id on finance_watchlist_items.

Revision ID: 0024_add_finance_watchlists
Revises: 0023_add_agent_personas
Create Date: 2026-11-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_add_finance_watchlists"
down_revision = "0023_add_agent_personas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "finance_watchlists" not in tables:
        op.create_table(
            "finance_watchlists",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_finance_watchlists_user_id", "finance_watchlists", ["user_id"])

    if "finance_watchlist_items" in tables:
        cols = {c["name"] for c in inspector.get_columns("finance_watchlist_items")}
        uqs = {u["name"] for u in inspector.get_unique_constraints("finance_watchlist_items") if u.get("name")}
        with op.batch_alter_table("finance_watchlist_items") as batch_op:
            if "list_id" not in cols:
                batch_op.add_column(sa.Column("list_id", sa.String(length=36), nullable=True))
                batch_op.create_foreign_key(
                    "fk_finance_watchlist_items_list_id",
                    "finance_watchlists",
                    ["list_id"],
                    ["id"],
                    ondelete="CASCADE",
                )
                batch_op.create_index("ix_finance_watchlist_items_list_id", ["list_id"])
            if "uq_finance_watchlist_user_symbol" in uqs:
                batch_op.drop_constraint("uq_finance_watchlist_user_symbol", type_="unique")
            if "uq_finance_watchlist_list_symbol" not in uqs:
                batch_op.create_unique_constraint("uq_finance_watchlist_list_symbol", ["list_id", "symbol"])


def downgrade() -> None:
    with op.batch_alter_table("finance_watchlist_items") as batch_op:
        batch_op.drop_constraint("uq_finance_watchlist_list_symbol", type_="unique")
        batch_op.drop_index("ix_finance_watchlist_items_list_id")
        batch_op.drop_column("list_id")
    op.drop_index("ix_finance_watchlists_user_id", table_name="finance_watchlists")
    op.drop_table("finance_watchlists")
