"""add pdf artifact enum values"""

from alembic import op


revision = "0002_add_pdf_artifact_types"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE artifact_type_enum ADD VALUE IF NOT EXISTS 'RESUME_PDF'")
    op.execute("ALTER TYPE artifact_type_enum ADD VALUE IF NOT EXISTS 'COVER_LETTER_PDF'")


def downgrade() -> None:
    # PostgreSQL ENUM value removal is not supported without a type rebuild.
    pass

