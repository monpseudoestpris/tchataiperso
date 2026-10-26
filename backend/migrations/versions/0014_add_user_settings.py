"""Add system_prompt and prompt_cache_enabled to users table.

Revision ID: 0014_add_user_settings
Revises: 0013_add_music_columns
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_add_user_settings"
down_revision = "0013_add_music_columns"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "users" in tables:
        existing_columns = {col["name"] for col in inspector.get_columns("users")}
        if "system_prompt" not in existing_columns:
            op.add_column(
                "users",
                sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
            )
        if "prompt_cache_enabled" not in existing_columns:
            op.add_column(
                "users",
                sa.Column("prompt_cache_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            )


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

