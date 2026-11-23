"""Add saved_videos table for user video library (links, full transcripts, summaries).

Revision ID: 0031_add_saved_videos
Revises: 0030_add_visual_doc_links
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_add_saved_videos"
down_revision = "0030_add_visual_doc_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "saved_videos" not in tables:
        op.create_table(
            "saved_videos",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("video_id", sa.String(length=32), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("author", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("duration", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("lang_label", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("thumbnail_url", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("has_transcript", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("transcript_segments", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("transcript_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("summary_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("summary_action", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("summary_model", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("analyses", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "video_id", name="uq_saved_videos_user_video"),
        )
        op.create_index("ix_saved_videos_user_id", "saved_videos", ["user_id"])
        op.create_index("ix_saved_videos_video_id", "saved_videos", ["video_id"])


def downgrade() -> None:
    raise RuntimeError("Downgrade destructif refusé; restaurez une sauvegarde complète de la base.")
