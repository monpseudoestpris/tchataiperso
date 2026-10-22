"""Add theme and keywords metadata columns to conversations.

Revision ID: 0006_add_conversation_metadata
Revises: 0005_add_generated_images
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_conversation_metadata"
down_revision = "0005_add_generated_images"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("conversations")}
    if "theme" not in columns:
        op.add_column("conversations", sa.Column("theme", sa.String(length=80), nullable=False, server_default=""))
    if "keywords" not in columns:
        op.add_column("conversations", sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

