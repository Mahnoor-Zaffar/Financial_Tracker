# FinTrack

Production-minded personal finance tracker built with Flask, SQLAlchemy, Flask-Login, WTForms, and Alembic migrations.

## Tech Stack

- Backend: Flask + app factory + blueprints
- ORM: SQLAlchemy
- Auth: Flask-Login session auth + password hashing
- Validation: Flask-WTF/WTForms + CSRF
- Database:
  - Local: SQLite
  - Production: PostgreSQL (`DATABASE_URL`)
- Frontend: Jinja + custom CSS/JS + Chart.js
- Migrations: Flask-Migrate / Alembic
- Runtime: Gunicorn (for production)
- Tests: Pytest

## Environment Configuration

Create a `.env` from `.env.example`:

```bash
cp .env.example .env
```

Key variables:

- `APP_ENV` / `FLASK_ENV`: `development`, `production`, or `testing`
- `SECRET_KEY`: required in production
- `DATABASE_URL`: PostgreSQL URL in production
- `SESSION_COOKIE_SECURE`: `true` behind HTTPS
- `LOG_LEVEL`: `INFO`, `WARNING`, etc.
- `TRANSACTIONS_PER_PAGE`, `MAX_TRANSACTIONS_PER_PAGE`

## Local Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure env:

```bash
cp .env.example .env
```

4. Apply migrations:

```bash
flask db upgrade
```

5. (Optional) Seed demo data:

```bash
flask seed demo
```

6. Run locally:

```bash
flask run --port 4848
```

Open `http://127.0.0.1:4848`.

Demo credentials after seed:

- `demo@fintrack.local`
- `ChangeMe123!`

## Database Migrations

Create migration after model changes:

```bash
flask db migrate -m "describe change"
flask db upgrade
```

## Test Suite

Run tests:

```bash
pytest -q
```

Current automated coverage includes:

- Auth flow (register, login, logout, login-required redirects)
- Transaction creation and validation
- Transfer integrity and account balance correctness
- Authorization boundary checks (cross-user edit/delete blocked)
- Filter + pagination behavior
- Budget overspend calculations
- Analytics summary series correctness

## Deployment

### Option A: Render

- Use the included [`render.yaml`](render.yaml).
- Provision a managed PostgreSQL database.
- Set `DATABASE_URL` in Render environment variables.
- `preDeployCommand` runs `flask db upgrade`.

Required production env:

- `APP_ENV=production`
- `FLASK_ENV=production`
- `SECRET_KEY` (strong random)
- `DATABASE_URL=postgresql+psycopg://...`
- `SESSION_COOKIE_SECURE=true`

### Option B: Docker

Build and run:

```bash
docker build -t fintrack .
docker run --rm -p 4848:4848 --env-file .env fintrack
```

The container startup command runs migrations, then serves via Gunicorn.

### Option C: Railway / Procfile platforms

- `Procfile` is included:
  - `web: gunicorn --bind 0.0.0.0:${PORT:-4848} app:app`
- Ensure env vars above are set.
- Run migrations as a release/pre-deploy command:
  - `flask db upgrade`

## Production Notes

- App now enforces non-default `SECRET_KEY` in production mode.
- Security headers are set (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`).
- Logging is configured to stdout with configurable log level (`LOG_LEVEL`).
- CSRF errors redirect safely with user feedback.

## Project Docs

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- UI system: [`docs/ui-system.md`](docs/ui-system.md)

## Completion Checklist

Implemented:

- Full auth and ownership-scoped CRUD flows
- Decimal-based finance calculations
- Transfer-safe balance math
- Dashboard/budget/reporting integration
- Responsive production UI with validated forms
- Error pages (`403`, `404`, `500`)
- Logging and production config hardening
- Automated tests for core auth/transaction/authorization flows
- Deployment assets (`Dockerfile`, `Procfile`, `render.yaml`)

Optional next steps:

- Add CI pipeline (lint + tests + migration check)
- Add password reset and email verification
- Add CSV import/export and recurring transaction scheduler
- Add rate limiting for auth endpoints
# Financial_Tracker
