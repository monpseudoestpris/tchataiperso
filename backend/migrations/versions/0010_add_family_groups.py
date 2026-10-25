"""Add family_groups table and family_group_id to users.

Revision ID: 0010_add_family_groups
Revises: 0009_add_deep_search_reports
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_add_family_groups"
down_revision = "0009_add_deep_search_reports"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "family_groups" not in existing_tables:
        op.create_table(
            "family_groups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False, server_default="Groupe familial"),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        )

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "family_group_id" not in user_columns:
        op.add_column("users", sa.Column("family_group_id", sa.String(length=36), nullable=True))
        try:
            op.create_foreign_key(
                "fk_users_family_group_id",
                "users",
                "family_groups",
                ["family_group_id"],
                ["id"],
                ondelete="SET NULL",
            )
        except Exception:
            pass
        op.create_index("ix_users_family_group_id", "users", ["family_group_id"])


def downgrade():
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")

