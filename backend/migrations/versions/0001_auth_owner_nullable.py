"""Add authentication tables and nullable data ownership columns.

Revision ID: 0001_auth_owner_nullable
Revises:
"""

from alembic import op
import sqlalchemy as sa

from app.models import Base

revision = "0001_auth_owner_nullable"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    inspector = sa.inspect(bind)
    for table in ("conversations", "attachments", "memories"):
        if "user_id" in {column["name"] for column in inspector.get_columns(table)}:
            continue
        with op.batch_alter_table(table, recreate="always" if bind.dialect.name == "sqlite" else "auto") as batch:
            batch.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))
            batch.create_foreign_key(f"fk_{table}_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE")
            batch.create_index(f"ix_{table}_user_id", ["user_id"], unique=False)


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
