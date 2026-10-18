"""Add reusable skills and conversation associations.

Revision ID: 0003_add_skills
Revises: 0002_require_data_owner
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_skills"
down_revision = "0002_require_data_owner"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "skills" not in existing:
        op.create_table(
            "skills",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_skills_user_id", "skills", ["user_id"])
    if "conversation_skills" not in existing:
        op.create_table(
            "conversation_skills",
            sa.Column("conversation_id", sa.String(length=36), nullable=False),
            sa.Column("skill_id", sa.String(length=36), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("conversation_id", "skill_id"),
            sa.UniqueConstraint("conversation_id", "position", name="uq_conversation_skills_position"),
        )


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")