"""Add deep_search_reports table.

Revision ID: 0009_add_deep_search_reports
Revises: 0008_add_blog_theme
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_add_deep_search_reports"
down_revision = "0008_add_blog_theme"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "deep_search_reports" not in existing:
        op.create_table(
            "deep_search_reports",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("conversation_id", sa.String(length=36), nullable=True),
            sa.Column("message_id", sa.String(length=36), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("topic", sa.Text(), nullable=False),
            sa.Column("markdown_content", sa.Text(), nullable=False),
            sa.Column("html_content", sa.Text(), nullable=False),
            sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_deep_search_reports_user_id", "deep_search_reports", ["user_id"])
        op.create_index("ix_deep_search_reports_conversation_id", "deep_search_reports", ["conversation_id"])
        op.create_index("ix_deep_search_reports_message_id", "deep_search_reports", ["message_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

