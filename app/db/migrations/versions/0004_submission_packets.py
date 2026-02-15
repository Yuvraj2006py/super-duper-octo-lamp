"""add submission packets table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_submission_packets"
down_revision = "0003_form_fields_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submission_packets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("response_url", sa.String(length=1024), nullable=True),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_submission_packets_application", "submission_packets", ["application_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_submission_packets_application", table_name="submission_packets")
    op.drop_table("submission_packets")
