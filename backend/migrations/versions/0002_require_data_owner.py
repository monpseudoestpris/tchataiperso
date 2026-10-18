"""Require ownership after legacy rows are explicitly assigned.

Revision ID: 0002_require_data_owner
Revises: 0001_auth_owner_nullable
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_require_data_owner"
down_revision = "0001_auth_owner_nullable"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for table in ("conversations", "attachments", "memories"):
        missing = bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE user_id IS NULL")).scalar_one()
        if missing:
            raise RuntimeError(f"{table} contient {missing} lignes sans propriétaire; attribuez-les avant cette migration.")
        with op.batch_alter_table(table, recreate="always" if bind.dialect.name == "sqlite" else "auto") as batch:
            batch.alter_column("user_id", existing_type=sa.String(length=36), nullable=False)


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
