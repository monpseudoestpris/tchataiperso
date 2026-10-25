"""Add sound_type, instrumental and model_id to generated_sounds table.

Revision ID: 0013_add_music_columns
Revises: 0012_add_generated_sounds
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_add_music_columns"
down_revision = "0012_add_generated_sounds"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "generated_sounds" in tables:
        existing_columns = {col["name"] for col in inspector.get_columns("generated_sounds")}
        if "sound_type" not in existing_columns:
            op.add_column(
                "generated_sounds",
                sa.Column("sound_type", sa.String(length=30), nullable=False, server_default="sound_effect"),
            )
        if "instrumental" not in existing_columns:
            op.add_column(
                "generated_sounds",
                sa.Column("instrumental", sa.Boolean(), nullable=True),
            )
        if "model_id" not in existing_columns:
            op.add_column(
                "generated_sounds",
                sa.Column("model_id", sa.String(length=50), nullable=True),
            )


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

