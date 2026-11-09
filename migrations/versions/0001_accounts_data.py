"""Create the initial schema or adopt a prototype database without losing rows.

The prototype's unique browser identifier prevented account switching. Removing
that constraint requires a users-table rebuild on SQLite (Alembic batch mode).
This schema snapshot deliberately does not import the mutable application models.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_accounts_data"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata = sa.MetaData()

    def id_column():
        return sa.Column("id", sa.Integer, primary_key=True, autoincrement=True)

    def user_id():
        return sa.Column("user_id", sa.Integer, nullable=False, index=True)

    def language_id():
        return sa.Column("language_id", sa.Integer, nullable=False, index=True)

    def created_at():
        return sa.Column("created_at", sa.DateTime, nullable=False)

    sa.Table("users", metadata,
        id_column(),
        sa.Column("login", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("cookie_id", sa.String(128), nullable=False, index=True),
        sa.Column("fingerprint", sa.String(128), nullable=False, index=True),
        sa.Column("ip_address", sa.String(64), nullable=False, index=True),
        created_at(), sa.Column("last_login", sa.DateTime, nullable=False),
    )
    sa.Table("sessions", metadata,
        sa.Column("token", sa.String(128), primary_key=True), user_id(), created_at(),
    )
    sa.Table("progress", metadata,
        id_column(), user_id(),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("xp", sa.Integer, nullable=False),
        sa.Column("streak", sa.Integer, nullable=False),
    )
    sa.Table("languages", metadata,
        id_column(),
        sa.Column("code", sa.String(8), nullable=False, unique=True, index=True),
        sa.Column("name_pl", sa.String(64), nullable=False),
        sa.Column("name_native", sa.String(64), nullable=False),
        sa.Column("flag_emoji", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
    )
    sa.Table("user_languages", metadata,
        id_column(), user_id(), language_id(), created_at(),
        sa.UniqueConstraint("user_id", "language_id", name="uq_user_language"),
    )
    sa.Table("user_words", metadata,
        id_column(), user_id(), language_id(),
        sa.Column("word", sa.String(128), nullable=False),
        sa.Column("translation_pl", sa.String(128), nullable=False),
        sa.Column("is_valid", sa.Boolean, nullable=False), created_at(),
    )
    sa.Table("study_sessions", metadata,
        id_column(), user_id(), language_id(),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("correct", sa.Integer, nullable=False),
        sa.Column("finished", sa.Boolean, nullable=False), created_at(),
        sa.Column("finished_at", sa.DateTime, nullable=True),
    )
    sa.Table("study_answers", metadata,
        id_column(), sa.Column("session_id", sa.Integer, nullable=False, index=True),
        sa.Column("word_id", sa.Integer, nullable=False),
        sa.Column("prompt", sa.String(128), nullable=False),
        sa.Column("expected", sa.String(128), nullable=False),
        sa.Column("given", sa.String(128), nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False), created_at(),
    )
    connection = op.get_bind()
    metadata.create_all(connection, checkfirst=True)
    constraints = sa.inspect(connection).get_unique_constraints("users")
    browser_constraints = [item for item in constraints if item["column_names"] == ["cookie_id"]]
    if browser_constraints:
        with op.batch_alter_table("users", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}) as batch:
            for item in browser_constraints:
                batch.drop_constraint(item["name"] or "uq_users_cookie_id", type_="unique")


def downgrade():
    raise RuntimeError("Restore a database backup to roll back this initial data-preserving migration.")
