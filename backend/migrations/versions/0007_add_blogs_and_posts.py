"""Add blogs and blog posts tables.

Revision ID: 0007_add_blogs_and_posts
Revises: 0006_add_conversation_metadata
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_add_blogs_and_posts"
down_revision = "0006_add_conversation_metadata"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "blogs" not in existing:
        op.create_table(
            "blogs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("auto_refresh", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_blogs_user_id", "blogs", ["user_id"])

    if "blog_posts" not in existing:
        op.create_table(
            "blog_posts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("blog_id", sa.String(length=36), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_blog_posts_blog_id", "blog_posts", ["blog_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

