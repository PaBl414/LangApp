"""Persist quiz drafts, start idempotency and accepted answer snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0002_reliable_quizzes"
down_revision = "0001_accounts_data"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_words", sa.Column("translation_alternatives", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("user_words", sa.Column("word_alternatives", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("study_answers", sa.Column("accepted_answers", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("study_sessions", sa.Column("current_index", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("study_sessions", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("study_sessions", sa.Column("start_request_id", sa.String(36), nullable=True))
    op.add_column("study_sessions", sa.Column("requested_count", sa.Integer(), nullable=True))
    op.create_index("uq_study_start_request", "study_sessions", ["user_id", "start_request_id"], unique=True)


def downgrade():
    raise RuntimeError("Restore a backup to avoid discarding saved drafts and answer alternatives.")
