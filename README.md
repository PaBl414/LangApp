# LangApp

LangApp is a small Polish-language vocabulary learning app. It provides account registration and login, language selection, personal word lists, dictionary lookups, and quiz sessions. The application consists of a FastAPI backend and a static HTML/CSS/JavaScript frontend.

> This project is a learning/demo application. It has not been reviewed or hardened for production use. Do not use it to store real personal data or expose it to the public internet without completing the security and privacy work described below.

## Features

- Account registration and cookie-based login sessions.
- A catalog of languages seeded from `backend/seed_languages.py`.
- User-owned language and vocabulary lists.
- Quiz sessions in either translation direction or mixed mode.
- Resumable quizzes with automatic drafts, local recovery and safe submission retries.
- Editable vocabulary with explicit accepted alternatives in both translation directions.
- Optional word suggestions and English dictionary lookup through third-party APIs.

## Requirements

- Python 3.11 or newer (Python 3.12 is also suitable).
- `pip` and `venv`.
- Internet access for the external dictionary lookup feature. No API key is required.

## Run locally

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m backend.seed_languages
python -m uvicorn backend.main:app --reload
```

Then open <http://127.0.0.1:8000>. The API documentation is available at <http://127.0.0.1:8000/docs>.

On macOS or Linux, replace the environment setup commands with:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend.seed_languages
python -m uvicorn backend.main:app --reload
```

The SQLite database is created at `data/langapp.db` relative to the project directory by default. Set `LANGAPP_DATABASE_URL` to use another SQLAlchemy async database URL. For example, `sqlite+aiosqlite:///./data/dev.db`.

## Database upgrades and sessions

Startup and the language seeder automatically run Alembic migrations. The initial
migration also adopts databases created by earlier LangApp versions: it preserves
existing rows and removes the unique constraint on browser identifiers, allowing
different accounts to log in on the same device. Stop other app processes and back
up an existing database before its first upgrade. For SQLite, copy the database
while the app is stopped, or use SQLite's backup API for an online backup.

You can also migrate explicitly from the repository root:

```sh
python -m alembic upgrade head
```

The initial migration supports upgrades only; restore a backup to roll it back.
For deployments with multiple workers, run the migration once before starting
workers instead of letting their first startup migrate concurrently.

Authentication sessions expire on the server after seven days. A successful
login replaces the session previously held by that browser; logout revokes its
token. Other devices keep their own sessions. The basic duplicate-registration
check still compares the combination of browser identifier, fingerprint and IP;
a browser identifier alone is not an account identifier.

Removing a language permanently deletes that user's words, quiz sessions,
recorded answers and progress for that language. Adding it again starts with an
empty list. Other users and other languages are unaffected.

## Project layout

```text
backend/       FastAPI app, data models, authentication and API routes
frontend/      Static pages, styles and browser JavaScript
migrations/    Versioned database schema and legacy database upgrades
tests/         Isolated API and migration regression tests
data/          Local SQLite data (ignored by Git)
requirements.txt
```

## API overview

The app serves its frontend and API from the same origin. Main route groups:

- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`
- `GET /api/me`, `GET /api/progress`
- `GET /api/languages`, `/api/user/languages` and related word routes
- `POST /api/study/start` and study answer/history routes
- `GET /api/study/active?language_id=...`, `GET /api/study/sessions/{id}`
- `PUT /api/study/sessions/{id}/draft`, `POST /api/study/submit`
- `PUT /api/words/{id}` for editing vocabulary and accepted alternatives
- `GET /api/dictionary/check`

Use `/docs` while the local server is running for the complete generated OpenAPI schema and request models.

## Quiz recovery and answer grading

- Starting from the browser creates a UUID request identifier. Retrying the same
  start request returns the same quiz, including its original question order.
  API clients should send `request_id` to get this guarantee. Reusing it with
  different settings is rejected with HTTP 409.
- Drafts contain the current question and entered answers. The browser saves
  them locally on input and synchronizes them to the server after a short pause.
  Refreshing the quiz URL restores the server draft and any pending local edits;
  the configuration screen also lists up to 20 recent unfinished quizzes.
- Draft updates use a revision number. A stale browser tab cannot overwrite a
  newer draft. Conflicting local text is kept until the user explicitly chooses
  to load the server version. Network retries of an already saved identical
  draft are safe.
- Completed results are immutable. Repeating submission returns the original
  result; reloading its quiz URL retrieves it even if the completion response was
  lost. The revision sent by the browser also protects finalization from stale
  drafts. Quiz ownership is checked on every endpoint.
- Local draft storage is separated by account and quiz. Successful synchronization
  removes the local copy. Explicit logout clears the current quiz's local copy;
  the user is warned if this would discard unsynchronized text. The local copy is
  browser data, not encrypted storage. If browser storage is blocked, a warning
  is shown and server saving still works. This is not an offline PWA: initially
  loading the application and authenticating require a server connection.
- Use **Edytuj** next to a word to add accepted Polish translations or foreign
  forms, one per line (up to 10 alternatives per direction, 128 characters each).
  Every quiz snapshots its accepted answers at start, so editing or deleting a
  vocabulary entry does not change the grading of an existing quiz. Removing an
  entire language still deletes its quizzes as documented above.
- Grading uses Unicode NFC, case folding, and collapsed whitespace. Accents,
  punctuation and spelling remain significant. Alternatives are explicit;
  commas or slashes in an existing translation are never automatically split.
  No fuzzy or AI-based grading is performed.

Migration `0002_reliable_quizzes` adds draft and alternative-answer fields with
defaults that preserve existing vocabulary and quiz rows. Existing quizzes keep
their original single expected answer. Back up an existing database before
upgrading, as described above.

## Privacy and security notes

Registration and login currently use a browser fingerprint, a persistent identifier stored in browser local storage, and the client IP address as inputs to a basic duplicate-account check. This is privacy-sensitive data. The app does not currently provide a privacy notice, retention policy, account deletion flow, or a production-grade anti-abuse design. Review these requirements before collecting data from other people.

For an HTTPS deployment, set `LANGAPP_COOKIE_SECURE=1` so authentication cookies are only sent over HTTPS. Keep it unset for local HTTP development. Do not run the development server with `--reload` in production. Use a production ASGI server behind HTTPS, add request rate limits and CSRF protections, configure trusted proxy handling deliberately, and use managed secret/configuration storage if secrets are introduced.

The database contains account identifiers, password hashes, session tokens, IP/fingerprint values and learning data. Keep it out of source control and back it up securely. New passwords use Argon2; existing bcrypt hashes are verified and upgraded to Argon2 after a successful login. Password hashes do not make the database safe to publish.

The dictionary route sends the queried word to third-party services (Free Dictionary API and Datamuse). Their availability and data practices are outside this project’s control.

## Development notes

- Seed or update the language catalog with `python -m backend.seed_languages`.
- Database schema changes belong in Alembic revisions under `migrations/`.
- Run regressions with `python -m unittest discover -s tests -v`. Tests use temporary SQLite databases and in-process ASGI requests, without opening a network port or changing the local application database. No additional test dependencies are required.
- API request models reject invalid types, oversized text, duplicate quiz answers and unknown fields with HTTP 422. Answers for words outside the selected quiz are rejected with HTTP 400. Word validation status is currently client-reported; it defaults to unverified and must be a JSON boolean, not a string.
- There is no CI workflow yet.
- No license is included. Add a license only after deciding which reuse terms you want to grant.
