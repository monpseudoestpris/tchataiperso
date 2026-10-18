"""Keep attachment extraction organized by page."""

from alembic import op
import sqlalchemy as sa

revision = "0004_attachment_extraction"
down_revision = "0003_add_skills"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("attachments")}
    if "extraction" not in columns:
        op.add_column("attachments", sa.Column("extraction", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("Downgrade destructif refuse ; restaurez une sauvegarde complete.")