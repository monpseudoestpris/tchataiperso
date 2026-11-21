"""Add external_links JSON column to visual_documents table.

Revision ID: 0030_add_visual_doc_links
Revises: 0029_add_visual_doc_category
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_add_visual_doc_links"
down_revision = "0029_add_visual_doc_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "visual_documents" in tables:
        existing_columns = {col["name"] for col in inspector.get_columns("visual_documents")}
        if "external_links" not in existing_columns:
            op.add_column(
                "visual_documents",
                sa.Column("external_links", sa.JSON(), nullable=False, server_default="[]"),
            )


def downgrade() -> None:
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
