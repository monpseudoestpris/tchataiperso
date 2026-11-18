"""Add note column on finance_watchlist_items.

Revision ID: 0025_add_watchlist_item_note
Revises: 0024_add_finance_watchlists
Create Date: 2026-11-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_add_watchlist_item_note"
down_revision = "0024_add_finance_watchlists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "finance_watchlist_items" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("finance_watchlist_items")}
        if "note" not in cols:
            with op.batch_alter_table("finance_watchlist_items") as batch_op:
                batch_op.add_column(
                    sa.Column("note", sa.String(length=240), nullable=False, server_default="")
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "finance_watchlist_items" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("finance_watchlist_items")}
        if "note" in cols:
            with op.batch_alter_table("finance_watchlist_items") as batch_op:
                batch_op.drop_column("note")
