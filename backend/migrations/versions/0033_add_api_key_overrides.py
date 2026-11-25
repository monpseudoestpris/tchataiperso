"""Add api_key_overrides table for AES-256-GCM encrypted API key overrides.

Revision ID: 0033_add_api_key_overrides
Revises: 0032_add_blog_topic_category
Create Date: 2026-11-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0033_add_api_key_overrides"
down_revision = "0032_add_blog_topic_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "api_key_overrides" not in tables:
        op.create_table(
            "api_key_overrides",
            sa.Column("key_name", sa.String(length=64), primary_key=True),
            sa.Column("ciphertext", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "updated_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_api_key_overrides_updated_by_user_id",
            "api_key_overrides",
            ["updated_by_user_id"],
        )


def downgrade() -> None:
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
