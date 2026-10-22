"""Add dedicated generated images gallery table.

Revision ID: 0005_add_generated_images
Revises: 0004_attachment_extraction
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_add_generated_images"
down_revision = "0004_attachment_extraction"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "generated_images" not in existing:
        op.create_table(
            "generated_images",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("aspect_ratio", sa.String(length=16), nullable=False, server_default="1:1"),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=120), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("storage_name", sa.String(length=100), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_generated_images_user_id", "generated_images", ["user_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

