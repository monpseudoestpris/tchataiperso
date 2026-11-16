"""Add kind, bricks to web_pages and canvas_files to web_page_versions.

Revision ID: 0022_add_webpage_apps_and_bricks
Revises: 0021_add_finance_moat
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_add_webpage_apps_and_bricks"
down_revision = "0021_add_finance_moat"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "web_pages" in tables:
        cols = {col["name"] for col in inspector.get_columns("web_pages")}
        if "kind" not in cols:
            op.add_column(
                "web_pages",
                sa.Column("kind", sa.String(20), nullable=False, server_default="page"),
            )
        if "bricks" not in cols:
            op.add_column(
                "web_pages",
                sa.Column("bricks", sa.JSON(), nullable=False, server_default="[]"),
            )

    if "web_page_versions" in tables:
        version_cols = {col["name"] for col in inspector.get_columns("web_page_versions")}
        if "canvas_files" not in version_cols:
            op.add_column(
                "web_page_versions",
                sa.Column("canvas_files", sa.JSON(), nullable=False, server_default="[]"),
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "web_page_versions" in tables:
        version_cols = {col["name"] for col in inspector.get_columns("web_page_versions")}
        if "canvas_files" in version_cols:
            op.drop_column("web_page_versions", "canvas_files")

    if "web_pages" in tables:
        cols = {col["name"] for col in inspector.get_columns("web_pages")}
        if "bricks" in cols:
            op.drop_column("web_pages", "bricks")
        if "kind" in cols:
            op.drop_column("web_pages", "kind")
