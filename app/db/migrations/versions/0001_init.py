"""initial schema"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    source_type_enum = sa.Enum("RSS", "MANUAL_JSON", "MANUAL_CSV", name="source_type_enum")
    job_status_enum = sa.Enum(
        "DISCOVERED",
        "PARSED",
        "SCORED",
        "DRAFTED",
        "VERIFIED",
        "READY_FOR_REVIEW",
        "APPROVED",
        "PACKET_BUILT",
        "SUBMITTED",
        "FOLLOWUP_SCHEDULED",
        "CLOSED",
        name="job_status_enum",
    )
    application_status_enum = sa.Enum(
        "DISCOVERED",
        "PARSED",
        "SCORED",
        "DRAFTED",
        "VERIFIED",
        "READY_FOR_REVIEW",
        "APPROVED",
        "PACKET_BUILT",
        "SUBMITTED",
        "FOLLOWUP_SCHEDULED",
        "CLOSED",
        name="application_status_enum",
    )
    artifact_type_enum = sa.Enum(
        "RESUME_DOCX",
        "COVER_LETTER_DOCX",
        "APPLICATION_PAYLOAD_JSON",
        "VERIFICATION_REPORT_JSON",
        name="artifact_type_enum",
    )
    message_status_enum = sa.Enum("DRAFT", "READY", "SENT", name="message_status_enum")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("profile_yaml", sa.Text(), nullable=False),
        sa.Column("profile_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "job_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("terms_url", sa.String(length=1024), nullable=True),
        sa.Column("automation_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("seniority", sa.String(length=100), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", job_status_enum, nullable=False),
        sa.Column("score_total", sa.Float(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["job_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_jobs_source_external"),
    )

    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_key", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("vector", Vector(256), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "chunk_key", "model_name", name="uq_embeddings_entity_chunk_model"
        ),
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("status", application_status_enum, nullable=False),
        sa.Column("verification_passed", sa.Boolean(), nullable=True),
        sa.Column("verification_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("claims_table", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("artifact_type", artifact_type_enum, nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", message_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_jobs_status_posted", "jobs", ["status", "posted_at"])
    op.create_index("idx_jobs_score_total", "jobs", ["score_total"])
    op.create_index("idx_jobs_raw_payload_gin", "jobs", ["raw_payload"], postgresql_using="gin")
    op.create_index("idx_jobs_score_breakdown_gin", "jobs", ["score_breakdown"], postgresql_using="gin")
    op.create_index("idx_applications_status_updated", "applications", ["status", "updated_at"])
    op.create_index("idx_audit_entity_created", "audit_log", ["entity_type", "entity_id", "created_at"])

    op.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_vector_ivfflat ON embeddings USING ivfflat (vector vector_cosine_ops) WITH (lists = 100)")


def downgrade() -> None:
    op.drop_index("idx_embeddings_vector_ivfflat", table_name="embeddings")
    op.drop_index("idx_audit_entity_created", table_name="audit_log")
    op.drop_index("idx_applications_status_updated", table_name="applications")
    op.drop_index("idx_jobs_score_breakdown_gin", table_name="jobs")
    op.drop_index("idx_jobs_raw_payload_gin", table_name="jobs")
    op.drop_index("idx_jobs_score_total", table_name="jobs")
    op.drop_index("idx_jobs_status_posted", table_name="jobs")

    op.drop_table("audit_log")
    op.drop_table("messages")
    op.drop_table("artifacts")
    op.drop_table("applications")
    op.drop_table("embeddings")
    op.drop_table("jobs")
    op.drop_table("job_sources")
    op.drop_table("users")

    sa.Enum(name="message_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="artifact_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="application_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="job_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_type_enum").drop(op.get_bind(), checkfirst=True)
