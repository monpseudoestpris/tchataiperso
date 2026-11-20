"""Add visual_documents and conversation_visual_docs tables.

Revision ID: 0027_add_visual_documents
Revises: 0026_add_finance_report_extracts
Create Date: 2026-11-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_add_visual_documents"
down_revision = "0026_add_finance_report_extracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "visual_documents" not in tables:
        op.create_table(
            "visual_documents",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("source_type", sa.String(length=20), nullable=False, server_default="pdf"),
            sa.Column("ocr_model", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("vision_enriched", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("figure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("compiled_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("pages_meta", sa.JSON(), nullable=False),
            sa.Column("warnings", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_visual_documents_user_id", "visual_documents", ["user_id"])
        op.create_index("ix_visual_documents_slug", "visual_documents", ["slug"], unique=True)

    if "conversation_visual_docs" not in tables:
        op.create_table(
            "conversation_visual_docs",
            sa.Column(
                "conversation_id",
                sa.String(length=36),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "visual_doc_id",
                sa.String(length=36),
                sa.ForeignKey("visual_documents.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.UniqueConstraint("conversation_id", "position", name="uq_conversation_visual_docs_position"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "conversation_visual_docs" in tables:
        op.drop_table("conversation_visual_docs")
    if "visual_documents" in tables:
        op.drop_index("ix_visual_documents_slug", table_name="visual_documents")
        op.drop_index("ix_visual_documents_user_id", table_name="visual_documents")
        op.drop_table("visual_documents")
