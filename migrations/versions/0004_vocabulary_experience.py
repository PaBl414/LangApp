"""Context examples, owned tags and a seven-day vocabulary recycle bin."""
from alembic import op
import sqlalchemy as sa

revision = "0004_vocabulary_experience"
down_revision = "0003_learning_progress"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("user_words", "study_answers"):
        op.add_column(table, sa.Column("example_sentence", sa.String(500), nullable=False, server_default=""))
        op.add_column(table, sa.Column("example_translation", sa.String(500), nullable=False, server_default=""))
    op.add_column("user_words", sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("user_words", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_user_words_trash", "user_words", ["user_id", "language_id", "deleted_at"])
    op.add_column("study_sessions", sa.Column("tag", sa.String(32), nullable=True))


def downgrade():
    raise RuntimeError("Restore a database backup to downgrade without losing vocabulary metadata.")
