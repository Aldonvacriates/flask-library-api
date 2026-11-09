# flask-library-api

A Flask REST API for a small library's members, books and loans, with JWT login, Redis-backed rate limiting and response caching, and a lightweight browser dashboard on top.

Built as a Coding Temple back-end course project (February to March 2026). There is no public deployment at the moment. The Railway files below are configuration only.

## Features

- CRUD endpoints for members, books and loans. A loan links one member to many books through a `loan_books` association table.
- JWT access tokens (15 minutes) and refresh tokens (30 days) via Flask-JWT-Extended.
- Member passwords hashed with Werkzeug on create and update.
- Book search across title, author, genre and description (`GET /books/search?q=`), capped at 50 results.
- Per-route rate limits with Flask-Limiter. Limit breaches return a JSON `429` body.
- Cached list and detail reads with Flask-Caching (60 seconds), cleared when a write touches that resource.
- A server-rendered home page (register / log in) and a dashboard (add and browse books, borrow books, view your loans), written in vanilla JavaScript.
- `/health` endpoint, a Gunicorn config and `railway.json` for deployment.

## Tech stack

Python, Flask 3.1, SQLAlchemy 2.0 (typed `Mapped` models), Flask-SQLAlchemy, Marshmallow / marshmallow-sqlalchemy, Flask-JWT-Extended, Flask-Limiter, Flask-Caching, MySQL (mysql-connector-python), Redis, Gunicorn, and vanilla JavaScript with Jinja templates.

## How it works

- **The config class is chosen from the environment** (`app.py`, `config.py`):
  - `APP_CONFIG` picks the class explicitly.
  - If it is not set, the app switches to `ProductionConfig` when Railway environment variables are present. Otherwise it uses `DevelopmentConfig`.
  - The database URL is read from `DATABASE_URL`, `MYSQL_URL` or `MYSQL_PUBLIC_URL`, or assembled from the individual `MYSQLHOST` / `MYSQLUSER` / ... variables. A `mysql://` URL is rewritten to use the `mysqlconnector` driver.
- **Production refuses to boot with unsafe defaults** (`validate_runtime_config` in `app/__init__.py`). With `ProductionConfig`, startup raises an error if any of these still has its local default:
  - the JWT secret
  - the database URL
  - the limiter's Redis URL
  - the cache's Redis URL
- **Rate limits are keyed per user, not just per IP** (`app/extensions.py`):
  - The key function optionally verifies the JWT. It keys by `user:<id>` when a valid token is present and falls back to `ip:<address>`.
  - Limit values live in `BaseConfig` in `config.py`:
    - login: 5 per minute
    - refresh: 10 per minute
    - heavy list reads: 20 per minute
    - search: 10 per minute
    - default for other routes: 200 per day and 50 per hour
    - application-wide: 1000 per hour
- **Cache invalidation is explicit** (`app/blueprints/*/routes.py`):
  - Each blueprint builds its own cache keys, such as `books:list` and `books:detail:<id>`.
  - Its create, update and delete handlers delete the matching keys after committing.
- **Legacy passwords are upgraded on login** (`app/blueprints/auth/routes.py`). Login checks the Werkzeug hash. If a stored password is still plaintext from an older record, it is accepted once and re-saved as a hash.

## API

All JSON. Protected routes need `Authorization: Bearer <access_token>`. "Cached" means a 60-second response cache.

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/login` | none | Returns `access_token` and `refresh_token`. 5/min |
| POST | `/auth/refresh` | refresh token | Returns a new access token. 10/min |
| POST | `/members/` | none | Register: `name`, `email`, `password`, optional `DOB` |
| GET | `/members/` | none | Cached, 20/min |
| GET | `/members/me` | JWT | Current member |
| GET | `/members/<id>` | none | Cached |
| PUT | `/members/<id>` | none | Partial update, re-hashes password |
| DELETE | `/members/<id>` | none | Also deletes that member's loans |
| POST | `/books/` | JWT | `title`, `author`, `genre`, `desc` |
| GET | `/books/` | none | Cached, 20/min |
| GET | `/books/search?q=<term>` | none | 10/min |
| GET | `/books/<id>` | none | Cached |
| PUT | `/books/<id>` | none | Partial update |
| DELETE | `/books/<id>` | none | |
| POST | `/loans/` | JWT | `loan_date`, `member_id` (must be your own), optional `book_ids` |
| GET | `/loans/me` | JWT | Current member's loans, 20/min |
| GET | `/loans/` | none | Cached, 20/min |
| GET | `/loans/<id>` | none | Cached |
| PUT | `/loans/<id>` | JWT | Partial update, can replace `book_ids` |
| DELETE | `/loans/<id>` | JWT | |
| GET | `/health` | none | `{"status": "ok"}` |
| GET | `/`, `/dashboard` | none | Browser UI. Tokens are kept in `localStorage` |

### Auth status

- `PUT` and `DELETE /loans/<id>` were changed to require a JWT, matching the other loan writes.
- They do not check ownership yet: any logged-in member can edit or delete any loan.
- `PUT` and `DELETE` on `/members/<id>` and `/books/<id>` are still unauthenticated.

`My-Library.postman_collection.json` covers the member, book and loan routes. Its requests do not send an `Authorization` header, so add a Bearer token yourself for the protected ones.

## Getting started

### Prerequisites

- Python 3.9 or newer (the minimum for Flask 3.1; developed on 3.13)
- MySQL with an empty database, for example `CREATE DATABASE library_db;`
- Redis (optional locally)

Without Redis, development uses `SimpleCache`, and the limiter falls back to in-memory limits of 200 per day and 50 per hour.

### Install

```bash
python -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Environment variables

The app reads only real environment variables. Nothing loads a `.env` file automatically, so export the values in your shell or set them on your host. `.env.example` lists every variable with placeholder values.

| Variable | Needed for | Purpose |
|---|---|---|
| `APP_CONFIG` | optional | `DevelopmentConfig`, `TestingConfig` or `ProductionConfig` |
| `DATABASE_URL` | dev and prod | SQLAlchemy URL, e.g. `mysql+mysqlconnector://user:password@localhost:3306/library_db` |
| `MYSQL_URL`, `MYSQL_PUBLIC_URL`, `MYSQLHOST`, `MYSQLPORT`, `MYSQLUSER`, `MYSQLPASSWORD`, `MYSQLDATABASE` | prod alternative | Railway MySQL variables, used when `DATABASE_URL` is not set |
| `JWT_SECRET_KEY` | prod (required) | Signs tokens. Production refuses the built-in placeholder |
| `REDIS_URL` / `REDIS_PUBLIC_URL` | prod (required) | Shared Redis for the limiter and cache |
| `CACHE_REDIS_URL`, `RATELIMIT_STORAGE_URI` | optional | Separate Redis URLs for the cache and the limiter |
| `CACHE_TYPE` | optional | Defaults to `SimpleCache` in dev and `RedisCache` in prod |
| `AUTO_CREATE_TABLES` | first run | `true` runs `db.create_all()` on startup (there are no migrations) |
| `PORT` | optional | Port for `python app.py` (5000) and Gunicorn (8000) |
| `GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT` | optional | Defaults 1, 4 and 120 (`gunicorn.conf.py`) |

Without `DATABASE_URL`, development falls back to `mysql+mysqlconnector://root@localhost/library_db`, which has no password.

### Run

```powershell
# PowerShell
$env:APP_CONFIG = "DevelopmentConfig"
$env:DATABASE_URL = "mysql+mysqlconnector://root:your-local-password@localhost:3306/library_db"
$env:JWT_SECRET_KEY = "any-long-random-string"
$env:AUTO_CREATE_TABLES = "true"
python app.py
```

```bash
# bash
export APP_CONFIG=DevelopmentConfig
export DATABASE_URL="mysql+mysqlconnector://root:your-local-password@localhost:3306/library_db"
export JWT_SECRET_KEY="any-long-random-string"
export AUTO_CREATE_TABLES=true
python app.py
```

Then open `http://127.0.0.1:5000/` to register and log in. The dashboard is at `/dashboard`.

### Tests

There is no test suite yet. `TestingConfig` in `config.py` is set up for one: it uses in-memory SQLite, `SimpleCache` and in-memory rate-limit storage.

## Deploying to Railway

The repo is set up for Railway but is not currently deployed.

- **`railway.json`** builds with Railpack, starts `gunicorn app:app`, health-checks `/health`, and restarts on failure (up to 10 retries).
- **`gunicorn.conf.py`** binds to `$PORT`. Gunicorn needs Linux or macOS; on Windows, use `python app.py` locally.
- **Services:** add MySQL and Redis services to the Railway project. The app picks up their variables automatically (see the table above).
- **Variables to set yourself:** `JWT_SECRET_KEY`. Also set `AUTO_CREATE_TABLES=true` for the first boot if the database is empty.

## Project structure

```text
app.py                  entry point, config selection, optional create_all
config.py               Base/Development/Testing/Production config classes
gunicorn.conf.py        Gunicorn settings from env vars
railway.json            Railway build/deploy config
app/
  __init__.py           create_app(), production config guard, 429 handler
  extensions.py         cache, JWT, limiter (per-user key), Marshmallow
  models.py             Member, Book, Loan, loan_books
  blueprints/           auth, members, books, loans, frontend (routes + schemas)
  templates/, static/   home and dashboard UI
```

## What I'd improve next

- Add ownership or role checks to loan updates and deletes, and require auth on member and book updates and deletes.
- Add a pytest suite on top of `TestingConfig`, and run it in CI.
- Replace `AUTO_CREATE_TABLES` with Alembic migrations.
- Update the Postman collection to log in and send the Bearer token.
