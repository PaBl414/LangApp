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
- A dashboard with previous results, practiced-word counts, accuracy, daily streaks and difficult vocabulary.
- Scheduled daily reviews based on completed answers, tracked separately for both translation directions.
- Optional word suggestions and English dictionary lookup through third-party APIs.

## Requirements

- Python 3.11 or newer (Python 3.12 is also suitable).
- `pip` and `venv`.
- Internet access for optional external dictionary lookups. [Datamuse announces mandatory keys from February 1, 2027](https://www.datamuse.com/api/); key integration is not implemented yet.

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
- `GET /api/dashboard`, `GET /api/dashboard/history?limit=10&offset=0`
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

## History, progress and daily reviews

The dashboard distinguishes unfinished drafts from completed learning activity:

- **Przećwiczone słowa** counts distinct entries in the current vocabulary with
  review state for at least one direction. It means practiced, not mastered.
  Editing the learning content resets that word's review state; deleting it
  removes its review state. Previous quiz results remain unchanged.
- Quiz counts, answer totals and accuracy come from completed quiz snapshots,
  including answers for vocabulary entries later deleted. Drafts do not count.
  Accuracy is shown as unknown when there are no completed answers.
- History loads 10 results at a time, offers older pages, and links directly to
  the original result. The API limits pages to 50 items and enforces ownership.
- Current streaks count distinct calendar days with a completed quiz. A streak
  remains active if the last study day was today or yesterday; a longer gap
  resets the current streak. Several quizzes on one day count as one study day.
- `/api/progress` now returns real per-language statistics. Its legacy `xp`
  field is derived as 10 points per correct completed answer; the old prototype
  `progress` table is preserved but is no longer the source of these statistics.

### Scheduling rules (version 1)

Review state belongs to one account, word and translation direction. Practicing
foreign → Polish does not automatically credit Polish → foreign.

1. An incorrect answer resets the consecutive-correct count and is due today.
2. Consecutive correct answers schedule the next review after **1, 3, 7, 14, 30,
   then 60 days**. Further correct answers keep the 60-day maximum.
3. **Do powtórzenia dzisiaj** includes today's and overdue items. Each language
   and direction has a separate action. A review may contain even one word;
   ordinary random quizzes still require at least four vocabulary entries.
4. Due quizzes select the oldest due dates first, prioritizing entries whose last answer was incorrect
   among equally due items. They never include another user's words or future
   items. New words are scheduled after their first completed practice attempt.
5. A word appears among up to 10 difficult entries if it has a mistake and either
   a most recent mistake in one direction or combined accuracy below 80%.

This is a simple, deterministic schedule, not FSRS or an estimated memory model.
All updates occur in the same transaction as first quiz completion. Retrying a
completed submission cannot add attempts, change its result or award XP twice.
Old quiz snapshots cannot schedule vocabulary content edited since quiz start.

Study days use `LANGAPP_TIMEZONE` (default **Europe/Warsaw**), an IANA timezone
name; timestamps remain stored in UTC. `tzdata` supplies timezone information on
Windows. Configure the timezone consistently before deployment; changing it
changes calendar-day reporting, while existing stored due dates are retained.

API clients start a scheduled review with `source: "due"` and a single direction
in `mode` (`lang_to_pl` or `pl_to_lang`). `mix` is rejected for this source.
Ordinary quizzes default to `source: "all"`. Source is part of the start request's
idempotency settings. The browser's scope selector supports both modes.

Migration `0003_learning_progress` creates review state and replays eligible
completed historical answers once, in completion order. It skips deleted words,
changed snapshots, and unfinished quizzes. Existing quiz and vocabulary rows
are preserved. SQLite migration DDL and backfill run in one explicit transaction,
so a failed upgrade can be retried without a partially applied schema.

## Reliability checks

All browser API calls use a shared client with a 15-second timeout, readable
validation errors and explicit handling of network failures, invalid JSON and
non-JSON gateway errors. Writes are not automatically retried by this client;
quiz retry safety remains controlled by request IDs and revisions. Dashboard
refreshes also discard stale responses to prevent deleted data reappearing.

GitHub Actions runs on pushes and pull requests with read-only repository
permissions. It installs dependencies, runs `pip check`, compiles Python files
and runs isolated regression tests on **Python 3.11 and 3.12**. A separate
**Node.js 24** job checks JavaScript syntax and tests shared API error handling.
Action versions are pinned by commit SHA. CI results become available after
the workflow is pushed to GitHub; configuring it locally does not run remote CI.

Run the same Python checks locally:

```sh
python -m pip check
python -m compileall -q backend migrations tests
python -m unittest discover -s tests -v
```

With Node.js 24 installed, run the dependency-free API client tests:

```sh
node --test tests/api-client.test.mjs
```

Node.js is only needed for developer checks, not to serve the application. The
small `frontend/js/package.json` declares the existing browser modules as ESM
for these checks; no npm install or frontend build step is required. Python and
API-client regressions do not start a network listener or modify the real app DB.

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
- CI configuration is in `.github/workflows/checks.yml`.
- No license is included. Add a license only after deciding which reuse terms you want to grant.
