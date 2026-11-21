"""Add default_voice to users table.

Revision ID: 0028_add_user_default_voice
Revises: 0027_add_visual_documents
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_add_user_default_voice"
down_revision = "0027_add_visual_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" in tables:
        existing_columns = {col["name"] for col in inspector.get_columns("users")}
        if "default_voice" not in existing_columns:
            op.add_column(
                "users",
                sa.Column("default_voice", sa.String(length=40), nullable=True),
            )


def downgrade() -> None:
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
