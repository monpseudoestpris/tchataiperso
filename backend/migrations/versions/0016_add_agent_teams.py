"""Add agent_teams table for multi-agent deliberations and saved teams.

Revision ID: 0016_add_agent_teams
Revises: 0015_add_auto_memory
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_add_agent_teams"
down_revision = "0015_add_auto_memory"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_teams" not in existing:
        op.create_table(
            "agent_teams",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("mode", sa.String(length=30), nullable=False, server_default="synthesis"),
            sa.Column("agents", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_agent_teams_user_id", "agent_teams", ["user_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

