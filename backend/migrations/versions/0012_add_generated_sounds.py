"""Add generated_sounds table for ElevenLabs sound effects.

Revision ID: 0012_add_generated_sounds
Revises: 0011_add_learn_reports
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_add_generated_sounds"
down_revision = "0011_add_learn_reports"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "generated_sounds" not in existing:
        op.create_table(
            "generated_sounds",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("prompt_influence", sa.Float(), nullable=True),
            sa.Column("output_format", sa.String(length=50), nullable=False, server_default="mp3_44100_128"),
            sa.Column("loop", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=120), nullable=False, server_default="audio/mpeg"),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("storage_name", sa.String(length=100), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_generated_sounds_user_id", "generated_sounds", ["user_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

