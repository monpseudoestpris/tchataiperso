"""Add auto_memory_enabled to users table.

Revision ID: 0015_add_auto_memory
Revises: 0014_add_user_settings
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_add_auto_memory"
down_revision = "0014_add_user_settings"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "users" in tables:
        existing_columns = {col["name"] for col in inspector.get_columns("users")}
        if "auto_memory_enabled" not in existing_columns:
            op.add_column(
                "users",
                sa.Column("auto_memory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            )


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

