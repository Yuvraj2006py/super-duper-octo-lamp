"""add application form fields and job platform"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_form_fields_platform"
down_revision = "0002_add_pdf_artifact_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("platform", sa.String(length=50), nullable=True))
    op.create_index("idx_jobs_platform", "jobs", ["platform"])

    op.create_table(
        "application_form_fields",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("field_key", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("platform", sa.String(length=50), nullable=False, server_default="generic"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "field_key", name="uq_application_form_fields_job_key"),
    )
    op.create_index("idx_application_form_fields_job_id", "application_form_fields", ["job_id"])
    op.create_index("idx_application_form_fields_platform", "application_form_fields", ["platform"])


def downgrade() -> None:
    op.drop_index("idx_application_form_fields_platform", table_name="application_form_fields")
    op.drop_index("idx_application_form_fields_job_id", table_name="application_form_fields")
    op.drop_table("application_form_fields")

    op.drop_index("idx_jobs_platform", table_name="jobs")
    op.drop_column("jobs", "platform")
