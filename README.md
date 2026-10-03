# IGotYourBack

A personal task desk with an AI planner that breaks goals into tasks — and never sends an email or books a calendar event without your explicit sign-off first.

**Live:** [igotyourback-task-manager.vercel.app](https://igotyourback-task-manager.vercel.app/)

![screenshot](docs/screenshot.png)
<!-- swap in a real screenshot or GIF of the board + AI planner -->

## Why this exists

Most task managers either do nothing smart, or hand an AI agent the keys and let it act on your behalf sight-unseen. This one splits the difference: the planner (Gemini) proposes tasks and drafts calendar/email content, but every AI-drafted action sits in a **pending** state until a human approves it. Nothing leaves the app without that step.

## Features

- **Board view** — To do → In progress → Completed, with search and priority/status filters
- **AI goal breakdown** — describe a goal, get 4–6 concrete tasks with priority, time estimate, and due date, generated with awareness of what's already on your plate
- **Plan my day** — pulls open tasks into a time-boxed daily plan (in-progress first, then by due date, capped at ~3 hours)
- **Human-approved actions** — AI can draft a calendar event or email for a task, but it only sends after you review and approve it
- **Graceful AI fallback** — if the Gemini API is unavailable or unset, a local rule-based planner takes over instead of failing outright

## Tech stack

- **Backend:** Django 5
- **AI:** Google Gemini (`google-genai`), with automatic fallback across `gemini-2.5-flash` → `2.0-flash` → `1.5-flash`
- **DB:** SQLite locally; Postgres in production via `DATABASE_URL` (`dj-database-url` + `psycopg`)
- **Static files:** WhiteNoise
- **Hosting:** Vercel (serverless WSGI)

## Running locally

```bash
git clone https://github.com/asthagothi/Igotyourback-task-manager.git
cd Igotyourback-task-manager
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in the values below
python manage.py migrate
python manage.py runserver
```

Visit `http://127.0.0.1:8000`.

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes in production | dev-only fallback locally | App won't boot on Vercel without this set |
| `DJANGO_DEBUG` | No | `False` on Vercel, `True` locally | |
| `GEMINI_API_KEY` | No | — | Without it, the local fallback planner is used instead |
| `DATABASE_URL` | No | SQLite | Set to a Postgres URL for persistent storage in production |
| `DATABASE_SSL` | No | `true` | |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | No | — | Leave unset to use the console backend (prints emails to the terminal, sends nothing) |
| `DEFAULT_FROM_EMAIL` | No | `IGotYourBack <desk@localhost>` | |

## Architecture notes

- **Approval-gated side effects:** AI-drafted calendar/email actions are stored as `PendingAction` records and only executed on explicit approval — see `tasks/models.py::PendingAction.execute()`.
- **Untrusted-output handling:** Gemini's JSON response is parsed defensively — code fences stripped, priority values whitelisted, dates validated, strings length-capped — before anything touches the database (`tasks/ai_service.py::_normalize`).
- **Serverless-aware settings:** `config/settings.py` branches on the `VERCEL` env var for database, static roots, and debug defaults; migrations run automatically on cold start (`config/wsgi.py`).

## Known limitations

- No test suite yet
- Single-user, no auth — anyone with the URL can see/edit all tasks

## License

MIT (or your choice — add a `LICENSE` file)
