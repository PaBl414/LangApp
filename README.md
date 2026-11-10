# LangApp

LangApp is a small Polish-language vocabulary learning app. It provides account registration and login, language selection, personal word lists, dictionary lookups, and quiz sessions. The application consists of a FastAPI backend and a static HTML/CSS/JavaScript frontend.

> This project is a learning/demo application. It has not been reviewed or hardened for production use. Do not use it to store real personal data or expose it to the public internet without completing the security and privacy work described below.

## Features

- Account registration and cookie-based login sessions.
- A catalog of languages seeded from `backend/seed_languages.py`.
- User-owned language and vocabulary lists.
- An always-visible vocabulary entry row below the word list, with separate foreign-word and Polish-translation fields.
- Optional pasted spreadsheet columns, live preview and atomic duplicate-safe batch saving.
- Quiz sessions in either translation direction or mixed mode.
- Resumable quizzes with automatic drafts, local recovery and safe submission retries.
- Editable vocabulary with explicit accepted alternatives in both translation directions.
- A dashboard with previous results, practiced-word counts, accuracy, daily streaks and difficult vocabulary.
- Scheduled daily reviews based on completed answers, tracked separately for both translation directions.
- A focused dashboard with one next learning action, searchable vocabulary and a consistent responsive dark interface.
- Ungraded flashcards and matching-pair warmups, including flashcards for mistakes from a completed quiz.
- Optional multilingual dictionary checks with a browser toggle and a server-wide off switch.

## Requirements

- Python 3.11 or newer (Python 3.12 is also suitable).
- `pip` and `venv`.
- Internet access for optional Wiktionary / Free Dictionary API lookups. No API key is required; saving and studying words do not require these services.

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
- `POST /api/user/languages/{language_id}/words/import` for atomic quick entry (1–100 pairs)
- `GET /api/dictionary/config`, `GET /api/dictionary/check`

Use `/docs` while the local server is running for the complete generated OpenAPI schema and request models.

## Interface and learning flow

The dashboard puts the next learning action first, followed by language cards,
compact statistics and today's reviews. History and difficult vocabulary remain
available under **Historia i szczegóły postępu**, collapsed initially. The main
action prefers the latest unfinished quiz owned by the current account, then
today's reviews, then a new quiz in a language with at least four words. With too
few words it opens the vocabulary; a new account is guided to language selection.
The dashboard API's `active_session` contains only the owned unfinished session's
ID, language, question cursor and total; it contains no answers.

Dashboard quick-start links use `quick=1`. The study page still authenticates,
loads vocabulary and checks the configuration before starting. Start requests
keep the existing UUID-based retry protection. Resuming a quiz continues to
restore server and local drafts rather than creating a new quiz.

The vocabulary page uses aligned word/translation/action columns, compact aliases
and search across foreign words, Polish translations and both sets of accepted
alternatives. Search ignores case and normalizes Unicode NFC. The adding row
always stays below the visible entries, including empty search results. Successful
saving clears the search so the new/updated word is visible. Newly added entries
are appended above the form. Existing dictionary checking and autocomplete remain
available in **Podpowiedzi i sprawdzanie słów**.

Quizzes show how many answers have actually been filled, with an accessible
progress bar. **Przejdź do pytania** expands a question map: filled questions are
marked separately from the current question. Navigation preserves the existing
automatic draft saving and stale-tab protection. Results start with a compact
summary; individual answers are under **Szczegóły odpowiedzi**. A failed submission
keeps the answers and permits the existing safe retry.

### Interactive warmups

The study configuration offers **Fiszki** and **Połącz pary** as separate,
ungraded warmups using the account's loaded vocabulary:

- **Fiszki** needs at least one word. Click the card or activate it with the
  keyboard to reveal the answer; move with the buttons or left/right arrows,
  shuffle, or change the translation direction. Accepted alternatives are shown
  on the answer side. Cards are not automatically marked mastered by revealing.
- **Połącz pary** selects up to four distinct pairs, shuffles each column and
  gives immediate feedback for each choice. Incorrect pairs stay available for
  another try. Completed pairs are disabled until a new round. Repeated primary
  words or translations are excluded to avoid ambiguous tasks; fewer than two
  distinct pairs shows guidance to use flashcards or add vocabulary.
- After a completed quiz, **Przećwicz błędne odpowiedzi na fiszkach** builds a
  deck only from incorrect result snapshots. It also works when the original
  vocabulary has subsequently changed. Returning from it restores the result.

Warmups make no quiz start/submission requests. They do not award XP, enter quiz
history, change the daily streak or schedule reviews. The UI states this explicitly;
complete a graded quiz to record learning progress. Warmup state exists only in
the current page. Ordinary quizzes still use server-side grading and scheduling.

The shared stylesheet now has one set of color, spacing, input, button, dialog and
feedback styles. Destructive confirmations use accessible native dialogs with
focus restoration; brief action confirmations use dismissible status toasts.
The interface supports small screens, visible keyboard focus, wrapped long text
and the system's reduced-motion preference. No fonts, images or UI libraries are
downloaded for this visual update. No database migration is required.

## Quick vocabulary entry

The language page always shows **Dodaj kolejne słowo** directly below all saved
words: a foreign-word field, a separate Polish-translation field and a
**Dodaj słowo** button. The row remains visible after saving; no dialog is needed.
New words appear at the end of the list, immediately above this row.

- Type the foreign word, press **Enter** or **Tab** to move to the translation,
  then press **Enter** or click **Dodaj słowo** to save.
- After a successful save, both fields clear and focus returns to the
  foreign-word field. A failed save preserves both fields for correction or retry.
- Empty fields are rejected. Identical pairs are skipped; a different primary
  translation for an existing word is a conflict and can be changed with **Edytuj**.
- This row uses the same atomic, duplicate-safe endpoint as batch entry. Saving
  never waits for a third-party dictionary. Optional checks run while typing.
- **Więcej opcji** opens the editor with dictionary lookup and optional accepted
  alternatives. The header's **+ Dodaj słowo** button focuses the always-visible row.

For optional bulk entry, expand **Wklej wiele słów (opcjonalnie)** below the row.
Use **Dodaj słowa jednym wpisem** to paste one pair per line:

```text
hello = cześć
house = dom
cat = kot
```

You can also copy two columns from a spreadsheet: foreign word first, Polish
translation second. The pasted tab separates the columns. This is a plain-text
paste format, not a CSV file importer; quoted fields with embedded newlines or
tabs are not supported. Each line must contain exactly one `=` or one tab
(a tab-separated translation can itself contain `=`). Commas and slashes remain
literal text and do not create accepted alternatives.

- The live preview shows the original line numbers, new entries, identical pairs
  to skip, and invalid or conflicting entries. Fix errors directly in the text.
  Blank lines are ignored; each side allows 1–128 Unicode characters after
  whitespace cleanup, with up to 100 pairs per request.
- Click **Dodaj słowa** or use **Ctrl+Enter** (macOS: **⌘+Enter**). Enter alone
  starts a new line. After success, the list updates immediately and focus
  returns to the empty input for the next entries.
- The server validates the entire batch and saves it in one transaction. An
  existing word with a different primary translation rejects the entire batch;
  use **Edytuj** to intentionally change it or add accepted alternatives.
- Identical pairs are skipped, including repetitions in the pasted text.
  Server duplicate matching uses the same Unicode NFC, case folding and
  whitespace cleanup as answer grading. The browser preview is a convenience;
  the server repeats validation against current data, including changes from
  other tabs. Existing spellings, alternatives, verification flags and review
  state are preserved when a duplicate is skipped.
- The input stays intact after an error. If a save response is lost, retrying
  the same list safely skips pairs already saved. Simultaneous imports and
  single-word additions serialize on the owned language membership.
- Leaving the page with an unsaved list requests the browser's standard discard
  confirmation. Explicit logout asks before discarding the list and clears it
  only after successful logout. Quick-entry text is not stored in browser storage;
  it does not survive closing or reloading the page after confirming the discard.
- Batch entry does not request external lookups. Existing server-cached positive
  checks may mark new entries as verified; otherwise they remain unverified.
  Unverified words have no warning badges and are available in quizzes.
- **Więcej opcji** retains the single-word dictionary check and optional
  accepted alternatives, collapsed until needed. **Zapisz i dodaj kolejne** keeps
  the editor open. Enter in the foreign-word field moves to the translation;
  Enter in the translation saves and opens the next pair when adding, or saves
  and closes when editing. Escape closes the editor when no save is in progress.

The batch endpoint accepts `{"words": [{"word": "hello", "translation_pl": "cześć"}]}`
and returns `added`, `skipped` and the resulting unique `words`. It rejects unknown
fields, including client-provided verification flags. It requires authentication
and a language belonging to that account. This feature needs no database upgrade.

## Optional dictionary checking

Use **Sprawdzaj słowa w słowniku** on the language page to turn checks on or off.
The setting is shared across language pages in the same browser and origin,
not stored on the user account. With browser storage blocked it still works
for the current page. Turning it off clears pending timers and advisory text;
already-started responses are ignored and no new lookups are sent. Other open
tabs follow changes through the browser's storage event.

Checks run after a 700 ms typing pause in the always-visible foreign-word field
and in the editor. Saving never starts or waits for a lookup, never asks for a
dictionary confirmation, and never blocks because a word was not found.
Unverified existing words no longer receive warning badges or error borders.
Input validation (required fields, length and duplicates) stays enabled.

### Autocomplete

From two characters, the same fields also show up to five verified word
completions. For example, type `hel` in English and choose `hello`. Click a
proposal, or use **Arrow Down / Arrow Up** and **Enter**. Selecting a proposal
fills the foreign-word field without saving the form or changing the Polish
translation. A following Enter moves to the translation as usual. Escape closes
the list; in the editor it dismisses an open suggestion list before closing the
dialog. Tab moves on without selecting. Text is never replaced automatically.

Candidates come from [MediaWiki prefix search](https://www.mediawiki.org/wiki/API:Prefixsearch)
in the selected language's Wiktionary edition, with English-edition fallback.
The strict profile preserves accents, and the server additionally filters titles
by the actual prefix, namespace, length and selected-language entry. Every
proposal must pass the same language-section check used for exact lookup before
being offered. Search results alone never mark a prefix as an existing word.

`GET /api/dictionary/check?lang=en&word=hel&suggest=true` runs exact checking and
completion concurrently, returning verified `suggestions` and a separate
`suggestions_status`. Without `suggest=true`, the existing exact-check behavior
is unchanged. Each completion lookup checks at most eight candidates, shares
in-flight work, has an eight-second deadline and reuses positive lexical checks.
A separate bounded cache holds up to 512 prefixes: positive completion lists for
60 seconds, other results for 15 seconds. Suggestions may be absent if there is
no matching entry, incomplete dictionary coverage or a service outage; saving
still works. The existing checkbox and server off switch disable autocomplete
as well as exact checking. Stale responses after further typing, leaving a field,
selecting a proposal or switching off cannot restore old proposals.

The lookup implementation uses:

- [Free Dictionary API](https://dictionaryapi.dev/) as the first English source.
- English Wiktionary's [language sections](https://en.wiktionary.org/wiki/Wiktionary:Entry_layout)
  for multilingual lookup and English fallback. It requests only section metadata
  through the [MediaWiki parsing API](https://www.mediawiki.org/wiki/API:Parsing_wikitext/TOCData),
  and confirms the selected language's level-two heading, not merely the existence
  of a page. Mappings cover 49 catalog codes. Cantonese (`yue`) returns
  `unsupported`, since a generic Chinese section does not confirm Cantonese.

Datamuse autocomplete is no longer used to decide whether a word exists.
Lookups preserve Unicode NFC, accents, hyphens and whole phrases, and try only
the supplied spelling, lowercase and initial-capital spelling. They do not
validate a phrase by finding its component words or accept fuzzy suggestions
as evidence. Dictionaries have incomplete coverage of inflections, names and
phrases; **not found is not a declaration that the word is incorrect**. The
checker does not validate the Polish translation or replace entered text without
the user's explicit selection.

`GET /api/dictionary/check?lang=de&word=Hund` returns a `status` of `found`,
`not_found`, `unavailable`, `unsupported` or `disabled`, plus the legacy `exists`
boolean, `source`, `matched_word`, `lang`, `word` and `suggestions` (empty unless
completion was requested).
HTTP 429/5xx, timeouts, malformed upstream responses and unexpected provider
errors are treated as temporary unavailability, not negative lexical evidence.
The UI presents each status as a neutral, non-blocking hint near the input.

The server bounds a lookup to 8 seconds in total (3 seconds per HTTP request),
with up to 8 concurrent outbound lookup operations per process. Identical
in-flight lookups share their work. An in-memory cache holds at most 1,024
entries per process: positive results for 6 hours, missing entries for 5 minutes
and temporary unavailability for 15 seconds. Cache entries disappear on restart.
Saving can reuse a positive result already in that worker's cache; it never
contacts a provider. The legacy `is_valid` request field remains accepted as a
strict boolean for old clients but is ignored. Existing verified flags are
preserved when editing an unchanged foreign word; flags do not grade quizzes.

To disable external dictionary checking for the entire app, set this environment
variable before starting the server:

```powershell
$env:LANGAPP_DICTIONARY_ENABLED = "0"
```

With this setting the UI toggle is disabled, `/check` returns `disabled`, and
dictionary checks make no outbound requests. Remove the variable or set it to
`1` and restart to enable checks again. `LANGAPP_DICTIONARY_USER_AGENT` can set a
deployment-specific descriptive User-Agent with contact information, following
the [Wikimedia User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy).
The default identifies LangApp and links to its repository. No database migration
or additional Python dependency is required.

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
**Node.js 24** job checks JavaScript syntax, shared API error handling,
dictionary toggle/response handling, vocabulary paste/search, continuation priority,
Polish count labels and non-ambiguous matching rounds. API regressions
also cover dictionary fallbacks/statuses/cache, atomic imports, retry safety,
concurrent writers, ownership and preserving review state when skipping duplicates.
Action versions are pinned by commit SHA. CI results become available after
the workflow is pushed to GitHub; configuring it locally does not run remote CI.

Run the same Python checks locally:

```sh
python -m pip check
python -m compileall -q backend migrations tests
python -m unittest discover -s tests -v
```

With Node.js 24 installed, run the dependency-free frontend tests:

```sh
node --test tests/*.test.mjs
```

Node.js is only needed for developer checks, not to serve the application. The
small `frontend/js/package.json` declares the existing browser modules as ESM
for these checks; no npm install or frontend build step is required. Python and
API-client regressions do not start a network listener or modify the real app DB.

## Privacy and security notes

Registration and login currently use a browser fingerprint, a persistent identifier stored in browser local storage, and the client IP address as inputs to a basic duplicate-account check. This is privacy-sensitive data. The app does not currently provide a privacy notice, retention policy, account deletion flow, or a production-grade anti-abuse design. Review these requirements before collecting data from other people.

For an HTTPS deployment, set `LANGAPP_COOKIE_SECURE=1` so authentication cookies are only sent over HTTPS. Keep it unset for local HTTP development. Do not run the development server with `--reload` in production. Use a production ASGI server behind HTTPS, add request rate limits and CSRF protections, configure trusted proxy handling deliberately, and use managed secret/configuration storage if secrets are introduced.

The database contains account identifiers, password hashes, session tokens, IP/fingerprint values and learning data. Keep it out of source control and back it up securely. New passwords use Argon2; existing bcrypt hashes are verified and upgraded to Argon2 after a successful login. Password hashes do not make the database safe to publish.

When checking is enabled, the dictionary route sends the queried foreign word
(not the Polish translation) to Free Dictionary API for English and to Wikimedia's
English Wiktionary when needed. Autocomplete also sends the entered prefix to
the selected language's Wiktionary edition and checks candidate entries in English
Wiktionary. Their availability and data practices are outside
this project's control. Disable checks in the browser or server configuration to
stop new external lookups. Server cache entries are shared lexical results, not
account data; they are held in memory and expire as described above.

## Development notes

- Seed or update the language catalog with `python -m backend.seed_languages`.
- Database schema changes belong in Alembic revisions under `migrations/`.
- Run regressions with `python -m unittest discover -s tests -v`. Tests use temporary SQLite databases and in-process ASGI requests, without opening a network port or changing the local application database. No additional test dependencies are required.
- API request models reject invalid types, oversized text, duplicate quiz answers and unknown fields with HTTP 422. Answers for words outside the selected quiz are rejected with HTTP 400. New word verification flags come only from positive server-cached dictionary results; absence of a result never prevents saving or learning.
- CI configuration is in `.github/workflows/checks.yml`.
- No license is included. Add a license only after deciding which reuse terms you want to grant.
