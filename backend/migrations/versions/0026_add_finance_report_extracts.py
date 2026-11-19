"""Add extracted_tables and extracted_at columns on finance_quarterly_reports.

Revision ID: 0026_add_finance_report_extracts
Revises: 0025_add_watchlist_item_note
Create Date: 2026-11-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_add_finance_report_extracts"
down_revision = "0025_add_watchlist_item_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "finance_quarterly_reports" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("finance_quarterly_reports")}
        with op.batch_alter_table("finance_quarterly_reports") as batch_op:
            if "extracted_tables" not in cols:
                batch_op.add_column(sa.Column("extracted_tables", sa.JSON(), nullable=True))
            if "extracted_at" not in cols:
                batch_op.add_column(sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "finance_quarterly_reports" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("finance_quarterly_reports")}
        with op.batch_alter_table("finance_quarterly_reports") as batch_op:
            if "extracted_at" in cols:
                batch_op.drop_column("extracted_at")
            if "extracted_tables" in cols:
                batch_op.drop_column("extracted_tables")
