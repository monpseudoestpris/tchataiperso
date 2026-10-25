"""Add learn_reports table.

Revision ID: 0011_add_learn_reports
Revises: 0010_add_family_groups
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_add_learn_reports"
down_revision = "0010_add_family_groups"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "learn_reports" not in existing:
        op.create_table(
            "learn_reports",
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
        op.create_index("ix_learn_reports_user_id", "learn_reports", ["user_id"])
        op.create_index("ix_learn_reports_conversation_id", "learn_reports", ["conversation_id"])
        op.create_index("ix_learn_reports_message_id", "learn_reports", ["message_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

