"""Add doc_category to visual_documents table.

Revision ID: 0029_add_visual_doc_category
Revises: 0028_add_user_default_voice
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_add_visual_doc_category"
down_revision = "0028_add_user_default_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "visual_documents" in tables:
        existing_columns = {col["name"] for col in inspector.get_columns("visual_documents")}
        if "doc_category" not in existing_columns:
            op.add_column(
                "visual_documents",
                sa.Column("doc_category", sa.String(length=40), nullable=False, server_default="general"),
            )


def downgrade() -> None:
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
