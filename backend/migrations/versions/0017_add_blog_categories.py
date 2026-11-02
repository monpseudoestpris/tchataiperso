"""Add categories column to blogs.

Revision ID: 0017_add_blog_categories
Revises: 0016_add_agent_teams
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_add_blog_categories"
down_revision = "0016_add_agent_teams"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {col["name"] for col in sa.inspect(bind).get_columns("blogs")}
    if "categories" not in columns:
        op.add_column(
            "blogs",
            sa.Column("categories", sa.JSON(), nullable=False, server_default='["news"]'),
        )


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

