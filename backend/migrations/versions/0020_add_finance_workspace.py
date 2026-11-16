"""Add finance workspace tables: watchlist, custom indicators, stock news, quarterly reports.

Revision ID: 0020_add_finance_workspace
Revises: 0019_add_creativity_params
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_add_finance_workspace"
down_revision = "0019_add_creativity_params"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "finance_watchlist_items" not in tables:
        op.create_table(
            "finance_watchlist_items",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("yahoo_symbol", sa.String(32), nullable=False, server_default=""),
            sa.Column("eod_ticker", sa.String(32), nullable=False, server_default=""),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("exchange", sa.String(80), nullable=False, server_default=""),
            sa.Column("currency", sa.String(16), nullable=False, server_default="EUR"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "symbol", name="uq_finance_watchlist_user_symbol"),
        )
        op.create_index("ix_finance_watchlist_items_user_id", "finance_watchlist_items", ["user_id"])

    if "finance_custom_indicators" not in tables:
        op.create_table(
            "finance_custom_indicators",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("formula", sa.Text(), nullable=False),
            sa.Column("pane", sa.String(20), nullable=False, server_default="overlay"),
            sa.Column("series_type", sa.String(20), nullable=False, server_default="line"),
            sa.Column("color", sa.String(30), nullable=False, server_default="#3b82f6"),
            sa.Column("guide_lines", sa.JSON(), nullable=False),
            sa.Column("enabled_by_default", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_finance_custom_indicators_user_id", "finance_custom_indicators", ["user_id"])

    if "finance_stock_news" not in tables:
        op.create_table(
            "finance_stock_news",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("company_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("search_query", sa.String(250), nullable=False, server_default=""),
            sa.Column("summary_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("articles", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_finance_stock_news_user_id", "finance_stock_news", ["user_id"])
        op.create_index("ix_finance_stock_news_symbol", "finance_stock_news", ["symbol"])

    if "finance_quarterly_reports" not in tables:
        op.create_table(
            "finance_quarterly_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("company_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("period_label", sa.String(60), nullable=False, server_default=""),
            sa.Column("source_type", sa.String(20), nullable=False, server_default="pdf"),
            sa.Column("filename", sa.String(255), nullable=False, server_default=""),
            sa.Column("storage_name", sa.String(100), nullable=True),
            sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("summary_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("key_metrics", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_finance_quarterly_reports_user_id", "finance_quarterly_reports", ["user_id"])
        op.create_index("ix_finance_quarterly_reports_symbol", "finance_quarterly_reports", ["symbol"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé ; restaurez une sauvegarde complète.")
