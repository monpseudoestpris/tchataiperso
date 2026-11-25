"""Add topic_category column to blogs.

Revision ID: 0032_add_blog_topic_category
Revises: 0031_add_saved_videos
"""

from alembic import op
import sqlalchemy as sa

revision = "0032_add_blog_topic_category"
down_revision = "0031_add_saved_videos"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {col["name"] for col in sa.inspect(bind).get_columns("blogs")}
    if "topic_category" not in columns:
        op.add_column(
            "blogs",
            sa.Column("topic_category", sa.String(length=60), nullable=False, server_default="general"),
        )


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
