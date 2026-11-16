"""Add finance_stock_moats table for stock MOAT analyses.

Revision ID: 0021_add_finance_moat
Revises: 0020_add_finance_workspace
"""

from alembic import op
import sqlalchemy as sa

revision = "0021_add_finance_moat"
down_revision = "0020_add_finance_workspace"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "finance_stock_moats" not in tables:
        op.create_table(
            "finance_stock_moats",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("company_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("moat_rating", sa.String(32), nullable=False, server_default="narrow"),
            sa.Column("moat_score", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("pillars", sa.JSON(), nullable=False),
            sa.Column("strengths", sa.JSON(), nullable=False),
            sa.Column("weaknesses", sa.JSON(), nullable=False),
            sa.Column("quantitative_signals", sa.JSON(), nullable=False),
            sa.Column("summary_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_finance_stock_moats_user_id", "finance_stock_moats", ["user_id"])
        op.create_index("ix_finance_stock_moats_symbol", "finance_stock_moats", ["symbol"])


def downgrade():
    op.drop_index("ix_finance_stock_moats_symbol", table_name="finance_stock_moats")
    op.drop_index("ix_finance_stock_moats_user_id", table_name="finance_stock_moats")
    op.drop_table("finance_stock_moats")
