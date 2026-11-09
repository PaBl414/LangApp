"""Create per-direction review state and backfill surviving, unchanged vocabulary."""
import os
import unicodedata
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

revision = "0003_learning_progress"
down_revision = "0002_reliable_quizzes"
branch_labels = None
depends_on = None


def upgrade():
    zone = ZoneInfo(os.getenv("LANGAPP_TIMEZONE", "Europe/Warsaw"))
    op.add_column("study_sessions", sa.Column("source", sa.String(8), nullable=False, server_default="all"))
    table = op.create_table(
        "word_reviews",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("word_id", sa.Integer, nullable=False),
        sa.Column("language_id", sa.Integer, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("correct_answers", sa.Integer, nullable=False),
        sa.Column("consecutive_correct", sa.Integer, nullable=False),
        sa.Column("due_on", sa.Date, nullable=False),
        sa.Column("last_correct", sa.Boolean, nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("user_id", "word_id", "direction", name="uq_word_review_direction"),
        sa.CheckConstraint("attempts >= 0 AND correct_answers >= 0 AND correct_answers <= attempts", name="ck_word_review_counts"),
        sa.CheckConstraint("consecutive_correct >= 0", name="ck_word_review_streak"),
    )
    op.create_index("ix_word_reviews_due", "word_reviews", ["user_id", "due_on", "language_id", "direction"])
    connection = op.get_bind()
    metadata = sa.MetaData()
    words = sa.Table("user_words", metadata, autoload_with=connection)
    sessions = sa.Table("study_sessions", metadata, autoload_with=connection)
    answers = sa.Table("study_answers", metadata, autoload_with=connection)
    intervals = (1, 3, 7, 14, 30, 60)

    def normalized(value):
        return unicodedata.normalize("NFC", " ".join(value.split())).casefold()

    query = sa.select(
        sessions.c.id.label("quiz_id"), sessions.c.user_id, sessions.c.language_id, sessions.c.finished_at,
        answers.c.word_id, answers.c.direction, answers.c.prompt, answers.c.expected,
        answers.c.accepted_answers, answers.c.is_correct,
        words.c.word, words.c.translation_pl, words.c.translation_alternatives, words.c.word_alternatives,
    ).join(answers, answers.c.session_id == sessions.c.id).join(words, words.c.id == answers.c.word_id).where(
        sessions.c.finished.is_(True), sessions.c.finished_at.is_not(None),
        words.c.user_id == sessions.c.user_id, words.c.language_id == sessions.c.language_id,
    ).order_by(sessions.c.finished_at, sessions.c.id, answers.c.id)
    states, seen = {}, set()
    for row in connection.execute(query):
        if row.direction not in {"lang_to_pl", "pl_to_lang"}:
            continue
        to_polish = row.direction == "lang_to_pl"
        prompt = row.word if to_polish else row.translation_pl
        primary = row.translation_pl if to_polish else row.word
        alternatives = row.translation_alternatives if to_polish else row.word_alternatives
        if normalized(prompt) != normalized(row.prompt) or {normalized(v) for v in [primary, *alternatives]} != {normalized(v) for v in [row.expected, *row.accepted_answers]}:
            continue
        event = (row.quiz_id, row.word_id, row.direction)
        if event in seen:
            continue
        seen.add(event)
        key = (row.user_id, row.word_id, row.direction)
        state = states.setdefault(key, {
            "user_id": row.user_id, "word_id": row.word_id, "language_id": row.language_id,
            "direction": row.direction, "attempts": 0, "correct_answers": 0, "consecutive_correct": 0,
        })
        state["attempts"] += 1
        state["correct_answers"] += int(row.is_correct)
        streak = state["consecutive_correct"] + 1 if row.is_correct else 0
        state["consecutive_correct"] = streak
        when = row.finished_at
        local_day = when.replace(tzinfo=timezone.utc).astimezone(zone).date()
        state["due_on"] = local_day + timedelta(days=intervals[min(streak - 1, 5)] if row.is_correct else 0)
        state["last_correct"] = row.is_correct
        state["last_reviewed_at"] = when
    rows = list(states.values())
    for offset in range(0, len(rows), 500):
        connection.execute(table.insert(), rows[offset:offset + 500])


def downgrade():
    raise RuntimeError("Restore a database backup rather than discarding learning history.")
