# FinTrack Architecture

## 1. Architecture Overview

- Pattern: Flask app factory with blueprints by domain (`auth`, `dashboard`, `transactions`, `finance`, `budgets`, `analytics`, `settings`).
- Data layer: SQLAlchemy models with user-owned boundaries, plus service-layer functions for financial calculations.
- Auth: Email/password login with `Flask-Login`, secure password hashing, session cookies, CSRF-protected forms.
- Configuration: Environment-based config with `.env` loading (`DATABASE_URL`, `SECRET_KEY`, cookie security flags).
- Database strategy:
  - Local dev default: SQLite (`instance/finance_tracker.db`)
  - Production: PostgreSQL via `DATABASE_URL`
- Migrations: `Flask-Migrate` wired into app factory (`flask db init/migrate/upgrade`).
- Frontend: Jinja templates + reusable macro components + custom CSS design system + Chart.js for analytics.

## 2. Folder Structure

```text
.
├── app.py
├── requirements.txt
├── .env.example
├── docs/
│   ├── architecture.md
│   └── ui-system.md
└── finance_tracker/
    ├── __init__.py
    ├── cli.py
    ├── config.py
    ├── extensions.py
    ├── blueprints/
    │   ├── auth/routes.py
    │   ├── dashboard/routes.py
    │   ├── transactions/routes.py
    │   ├── finance/routes.py
    │   ├── budgets/routes.py
    │   ├── analytics/routes.py
    │   └── settings/routes.py
    ├── forms/
    │   ├── auth.py
    │   ├── finance.py
    │   ├── transaction.py
    │   ├── budget.py
    │   ├── settings.py
    │   └── shared.py
    ├── models/
    │   ├── user.py
    │   ├── account.py
    │   ├── category.py
    │   ├── tag.py
    │   ├── transaction.py
    │   ├── budget.py
    │   └── base.py
    ├── services/
    │   ├── dashboard.py
    │   ├── analytics.py
    │   └── transactions.py
    ├── static/
    │   ├── css/app.css
    │   └── js/{app.js,charts.js}
    └── templates/
        ├── base.html
        ├── landing.html
        ├── auth/{login.html,register.html}
        ├── dashboard/index.html
        ├── transactions/{index.html,new.html,edit.html}
        ├── finance/{accounts.html,categories.html,tags.html}
        ├── budgets/{index.html,edit.html}
        ├── analytics/index.html
        ├── settings/profile.html
        └── components/{ui.html,forms.html}
```

## 3. Database Models Plan

### `users`
- `id`, `email (unique)`, `password_hash`, `full_name`, `currency_code`, `timezone`, timestamps.

### `accounts`
- `id`, `user_id`, `name`, `account_type`, `institution`, `opening_balance`, `is_active`, timestamps.
- Constraint: unique (`user_id`, `name`).

### `categories`
- `id`, `user_id`, `name`, `kind` (`income`/`expense`), `color`, timestamps.
- Constraint: unique (`user_id`, `name`, `kind`).

### `tags`
- `id`, `user_id`, `name`, `color`, timestamps.
- Constraint: unique (`user_id`, `name`).

### `transactions`
- `id`, `user_id`, `transaction_type` (`income`/`expense`/`transfer`), `amount`, `description`, `notes`, `occurred_on`,
  `account_id`, `transfer_account_id`, `category_id`, timestamps.
- Constraint: `amount > 0`.

### `transaction_tags` (association)
- `transaction_id`, `tag_id` (composite PK).

### `budgets`
- `id`, `user_id`, `category_id`, `month_start`, `amount_limit`, timestamps.
- Constraints: unique (`user_id`, `category_id`, `month_start`), `amount_limit > 0`.

## 4. Routes/Views Blueprint Plan

- `auth`
  - `GET/POST /auth/register`
  - `GET/POST /auth/login`
  - `POST /auth/logout`
- `dashboard`
  - `GET /` (public landing or authenticated dashboard)
  - `GET /dashboard`
- `transactions`
  - `GET /transactions/`
  - `GET/POST /transactions/new`
  - `GET/POST /transactions/<id>/edit`
  - `POST /transactions/<id>/delete`
- `finance`
  - `GET/POST /finance/accounts`
  - `GET/POST /finance/accounts/<id>/edit`
  - `POST /finance/accounts/<id>/delete`
  - `GET/POST /finance/categories`
  - `GET/POST /finance/categories/<id>/edit`
  - `POST /finance/categories/<id>/delete`
  - `GET/POST /finance/tags`
  - `GET/POST /finance/tags/<id>/edit`
  - `POST /finance/tags/<id>/delete`
- `budgets`
  - `GET/POST /budgets/`
  - `GET/POST /budgets/<id>/edit`
  - `POST /budgets/<id>/delete`
- `analytics`
  - `GET /analytics/`
- `settings`
  - `GET/POST /settings/profile`

## 5. Auth Flow

1. Register with email/password + profile name.
2. Password hashed with Werkzeug.
3. Login validates hash and starts secure session (`Flask-Login`).
4. Protected routes use `@login_required`.
5. Every model query in routes is user-scoped (`user_id == current_user.id`) for authorization boundaries.
6. Logout via CSRF-protected POST.

## 6. Implementation Roadmap

1. Finalize scaffold and baseline UI tokens/components.
2. Generate initial migration and apply locally.
3. Add full CRUD coverage (edit/delete for accounts/categories/tags/budgets).
4. Add pagination + export.
5. Add integration tests for auth, transaction permissions, and budget calculations.
6. Add deployment profile (Gunicorn, managed Postgres, secure env handling).

## 7. Key Tradeoffs

- Kept transfer support in a single `transactions` table for lower complexity and easier reporting.
- Chose calculated account balances over denormalized running balances to avoid drift and reconciliation bugs.
- Used server-rendered templates instead of SPA for maintainability, speed, and secure form handling.
