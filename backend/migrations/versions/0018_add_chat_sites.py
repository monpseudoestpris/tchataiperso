"""Attach immutable generated HTML pages to conversations."""

from alembic import op
import sqlalchemy as sa

revision = "0018_add_chat_sites"
down_revision = "0017_add_blog_categories"
branch_labels = None
depends_on = None


def upgrade():
    if "chat_sites" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "chat_sites",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36), nullable=False),
            sa.Column("input_hash", sa.String(64), nullable=False),
            sa.Column("scope", sa.String(20), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("html_content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("conversation_id", "input_hash", name="uq_chat_sites_input"),
        )
        op.create_index("ix_chat_sites_conversation_id", "chat_sites", ["conversation_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé ; restaurez une sauvegarde complète.")
