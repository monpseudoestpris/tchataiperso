"""Add theme column to blogs.

Revision ID: 0008_add_blog_theme
Revises: 0007_add_blogs_and_posts
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_add_blog_theme"
down_revision = "0007_add_blogs_and_posts"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {col["name"] for col in sa.inspect(bind).get_columns("blogs")}
    if "theme" not in columns:
        op.add_column("blogs", sa.Column("theme", sa.String(length=50), nullable=False, server_default="sunset"))


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

