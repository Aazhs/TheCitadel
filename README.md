# The Citadel

A Discord competitive-programming bot.

## Features

- `/ping` — Check bot latency and online status
- `/system-db-status` — Admin-only database connectivity check
- `/setup` — Admin-only server configuration (channels, alert role)
- `/start` — Member onboarding guide
- `on_member_join` — Automatic welcome messages
- `/link-codeforces <handle>` — Link your Codeforces profile
- `/unlink <platform>` — Remove your linked account
- `/my-profile` — View your competitive programming profile
- `/profile <member>` — View another member's profile
- `/upcoming` — View the next 5 upcoming Codeforces contests
- `/refresh-codeforces-contests` — (Admin only) Force a manual sync of Codeforces contests
- `/reminders status` — Check reminder status
- `/reminders list` — List upcoming scheduled contest reminders
- `/reminders enable` / `/reminders disable` — (Admin only) Toggle contest reminders
- `/reminders test` — (Admin only) Send a test reminder to the alert channel
- Structured logging with configurable log levels
- Environment-based configuration with validation
- Supabase PostgreSQL with SQLAlchemy async ORM
- Alembic database migrations
- Docker support

## Prerequisites

- Python 3.12+
- A [Discord Bot Token](https://discord.com/developers/applications)
- A [Supabase](https://supabase.com) project (for database features)

## Quick Start

### 1. Clone and set up the environment

```bash
git clone <your-repo-url>
cd Citadel
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set your DISCORD_TOKEN and DATABASE_URL
```

### 3. Run database migrations

```bash
alembic upgrade head
```

### 4. Run the bot

```bash
python -m src.main
```

### 5. Run with Docker

```bash
docker build -t algorithm-arena-bot .
docker run --env-file .env algorithm-arena-bot
```

## Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Go to **Project Settings → Database**
3. Under **Connection string**, select **URI** and copy the string
4. It will look like: `postgresql://postgres:[YOUR-PASSWORD]@db.[REF].supabase.co:5432/postgres`
5. Replace `[YOUR-PASSWORD]` with the database password you set when creating the project
6. Paste the full URI as `DATABASE_URL` in your `.env` file

> **Tip:** For local development, you can also use a local PostgreSQL instance:
> `DATABASE_URL=postgresql://postgres:password@localhost:5432/algorithm_arena`

## Environment Variables

| Variable        | Required | Default       | Description                              |
|-----------------|----------|---------------|------------------------------------------|
| `DISCORD_TOKEN` | ✅        | —             | Discord bot token                        |
| `DATABASE_URL`  | ❌        | —             | PostgreSQL connection string (Supabase)  |
| `ENVIRONMENT`   | ❌        | `development` | `development`, `staging`, or `production`|
| `LOG_LEVEL`     | ❌        | `INFO`        | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

## Database Migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/).

```bash
# Apply all pending migrations
alembic upgrade head

# Check current migration state
alembic current

# Generate a new migration after changing models
alembic revision --autogenerate -m "description of changes"

# Rollback one migration
alembic downgrade -1
```

> **Note:** `DATABASE_URL` must be set in your environment or `.env` file before running Alembic commands.

## Development

### Lint

```bash
ruff check src/ tests/
ruff format --check src/ tests/
```

### Test

```bash
pytest
```

Tests use in-memory SQLite and mocks — no live Supabase project is required.

### Format

```bash
ruff format src/ tests/
```

## Project Structure

```
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry-point
│   ├── config.py            # Pydantic Settings configuration
│   ├── bot.py               # Bot factory and extension loader
│   ├── cogs/
│   │   ├── __init__.py
│   │   ├── health.py        # /ping command
│   │   ├── admin_health.py  # /system-db-status command
│   │   ├── setup.py         # /setup command group
│   │   ├── onboarding.py    # /start + welcome messages
│   │   └── profile.py       # Profile linking and viewing
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py          # SQLAlchemy declarative base
│   │   ├── engine.py        # Async engine and session factory
│   │   └── models.py        # ORM models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── db_health.py     # Database health-check service
│   │   ├── guild_settings.py # Guild configuration CRUD
│   │   └── linked_accounts.py # Linked accounts CRUD
│   ├── providers/
│   │   ├── __init__.py
│   │   └── codeforces.py    # Codeforces API client
│   └── utils/
│       ├── __init__.py
│       └── logging.py       # Structured logging setup
├── migrations/
│   ├── env.py               # Alembic environment config
│   ├── script.py.mako       # Migration template
│   └── versions/
│       └── 0001_initial.py  # Initial tables
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Shared fixtures
│   ├── test_config.py       # Configuration tests
│   ├── test_db_models.py    # Model/schema tests
│   ├── test_db_health.py    # Health service tests
│   ├── test_guild_settings_service.py  # Guild settings tests
│   ├── test_setup_cog.py    # Setup cog tests
│   ├── test_onboarding_cog.py  # Onboarding cog tests
│   ├── test_codeforces_provider.py # CF provider tests
│   ├── test_linked_accounts_service.py # Linked accounts tests
│   └── test_profile_cog.py  # Profile cog tests
├── docs/
│   ├── discord-bot-setup.md    # Developer setup guide
│   └── server-configuration.md # Server admin guide
├── .env.example
├── .gitignore
├── alembic.ini
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Discord Bot Setup

See [docs/discord-bot-setup.md](docs/discord-bot-setup.md) for detailed instructions.

Quick version:

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to **Bot** → **Reset Token** → copy the token
4. Enable **Server Members Intent** in the Bot tab (required for welcome messages)
5. Go to **OAuth2 → URL Generator** → select `bot` + `applications.commands`
6. Select permissions: Send Messages, View Channels, Embed Links, Mention Everyone
7. Invite the bot to your server with the generated URL
8. Paste the token into your `.env` file

## Server Configuration

See [docs/server-configuration.md](docs/server-configuration.md) for the full admin guide.

## License

MIT
