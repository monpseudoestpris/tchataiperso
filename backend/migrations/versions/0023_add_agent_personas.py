"""Add agent_personas table for saved council personalities.

Revision ID: 0023_add_agent_personas
Revises: 0022_add_webpage_apps_and_bricks
Create Date: 2026-11-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_add_agent_personas"
down_revision = "0022_add_webpage_apps_and_bricks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "agent_personas" not in existing:
        op.create_table(
            "agent_personas",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("role", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("category", sa.String(length=40), nullable=False, server_default="personnalisé"),
            sa.Column("avatar", sa.String(length=20), nullable=False, server_default="🤖"),
            sa.Column("color", sa.String(length=30), nullable=False, server_default="#6366f1"),
            sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_personas_user_id", "agent_personas", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_personas_user_id", table_name="agent_personas")
    op.drop_table("agent_personas")
