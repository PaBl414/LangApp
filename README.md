# LangApp

LangApp is a small Polish-language vocabulary learning app. It provides account registration and login, language selection, personal word lists, dictionary lookups, and quiz sessions. The application consists of a FastAPI backend and a static HTML/CSS/JavaScript frontend.

> This project is a learning/demo application. It has not been reviewed or hardened for production use. Do not use it to store real personal data or expose it to the public internet without completing the security and privacy work described below.

## Features

- Account registration and cookie-based login sessions.
- A catalog of languages seeded from `backend/seed_languages.py`.
- User-owned language and vocabulary lists.
- Quiz sessions in either translation direction or mixed mode.
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

## Project layout

```text
backend/       FastAPI app, data models, authentication and API routes
frontend/      Static pages, styles and browser JavaScript
data/          Local SQLite data (ignored by Git)
requirements.txt
```

## API overview

The app serves its frontend and API from the same origin. Main route groups:

- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`
- `GET /api/me`, `GET /api/progress`
- `GET /api/languages`, `/api/user/languages` and related word routes
- `POST /api/study/start` and study answer/history routes
- `GET /api/dictionary/check`

Use `/docs` while the local server is running for the complete generated OpenAPI schema and request models.

## Privacy and security notes

Registration and login currently use a browser fingerprint, a persistent identifier stored in browser local storage, and the client IP address as inputs to a basic duplicate-account check. This is privacy-sensitive data. The app does not currently provide a privacy notice, retention policy, account deletion flow, or a production-grade anti-abuse design. Review these requirements before collecting data from other people.

For an HTTPS deployment, set `LANGAPP_COOKIE_SECURE=1` so authentication cookies are only sent over HTTPS. Keep it unset for local HTTP development. Do not run the development server with `--reload` in production. Use a production ASGI server behind HTTPS, add request rate limits and CSRF protections, configure trusted proxy handling deliberately, and use managed secret/configuration storage if secrets are introduced.

The database contains account identifiers, password hashes, session tokens, IP/fingerprint values and learning data. Keep it out of source control and back it up securely. Passwords are hashed; this does not make the database safe to publish.

The dictionary route sends the queried word to third-party services (Free Dictionary API and Datamuse). Their availability and data practices are outside this project’s control.

## Development notes

- Seed or update the language catalog with `python -m backend.seed_languages`.
- Database tables are created automatically at startup. There are no schema migrations yet; before changing an existing deployed schema, introduce a migration tool and migration scripts.
- The repository currently has no automated test suite or CI workflow.
- No license is included. Add a license only after deciding which reuse terms you want to grant.
