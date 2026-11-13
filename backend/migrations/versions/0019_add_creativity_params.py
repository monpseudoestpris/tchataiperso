"""Add creativity and sampling_params columns to conversations and skills.

Revision ID: 0019_add_creativity_params
Revises: 0018_add_chat_sites
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_add_creativity_params"
down_revision = "0018_add_chat_sites"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    conv_cols = {col["name"] for col in inspector.get_columns("conversations")}
    if "creativity" not in conv_cols:
        op.add_column("conversations", sa.Column("creativity", sa.Float(), nullable=True))
    if "sampling_params" not in conv_cols:
        op.add_column("conversations", sa.Column("sampling_params", sa.JSON(), nullable=True))

    if "skills" in inspector.get_table_names():
        skill_cols = {col["name"] for col in inspector.get_columns("skills")}
        if "creativity" not in skill_cols:
            op.add_column("skills", sa.Column("creativity", sa.Float(), nullable=True))
        if "sampling_params" not in skill_cols:
            op.add_column("skills", sa.Column("sampling_params", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("Downgrade destructif refusé ; restaurez une sauvegarde complète.")
