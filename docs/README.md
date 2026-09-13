# The Citadel

A Discord competitive-programming bot with an integrated personal productivity enforcer.

## Features

### Competitive Programming
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
- Weekly Coding Events — Create, publish, and manage custom server coding events with interactive registration
- Event Lifecycle — Automatic state transitions: `draft → published → active → submission_open → finalized`
- `/event-finalize` — (Admin only) Close submissions and finalize an event
- Result Submissions — Self-reported results via Discord modal with moderator approval flow
- `/submission-list` — (Admin only) List submissions for an event with optional status filter
- `/submission-approve` — (Admin only) Approve a pending submission
- `/submission-reject` — (Admin only) Reject a submission with required reason
- Audit Logging — All moderator and lifecycle actions are logged
- Structured logging with configurable log levels
- Environment-based configuration with validation
- Supabase PostgreSQL with SQLAlchemy async ORM
- Alembic database migrations
- Docker support

### Overwatch — Personal Productivity Enforcer

A private-channel system that pings you on a 15-minute loop, demands honest progress updates on whatever you're working on, and escalates — including hostile, unfiltered tone — if you go dark.

- **Private channel** — Auto-creates `#overwatch-zone` visible only to you and the bot
- **15-minute check-in loop** — Demands progress updates, parses intent via Gemini API
- **Escalating tone** — Neutral → Strict → Hostile (with profanity) as you ignore check-ins
- **Task queue** — Priority risk scoring, session tracking, time targets
- **Commands** — `!start`, `!status`, `!pause`, `!resume`, `!done`, `!queue`, `!skip`
- **Web dashboard** — FastAPI + Jinja2 dashboard showing tasks, sessions, activity log
- **Quiet hours** — Configurable hours where the bot leaves you alone

See [overwatch-setup.md](overwatch-setup.md) for setup instructions.

## Prerequisites

- Python 3.12+
- A [Discord Bot Token](https://discord.com/developers/applications)
- A [Supabase](https://supabase.com) project (for database features)
- A [Gemini API Key](https://aistudio.google.com/apikey) (for Overwatch, free tier)

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
# Edit .env and set your DISCORD_TOKEN, DATABASE_URL, and optionally Overwatch vars
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
docker build -t the-citadel-bot .
docker run --env-file .env the-citadel-bot
```

## Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Go to **Project Settings → Database**
3. Under **Connection string**, select **URI** and copy the string
4. It will look like: `postgresql://postgres:[YOUR-PASSWORD]@db.[REF].supabase.co:5432/postgres`
5. Replace `[YOUR-PASSWORD]` with the database password you set when creating the project
6. Paste the full URI as `DATABASE_URL` in your `.env` file

> **Tip:** For local development, you can also use a local PostgreSQL instance:
> `DATABASE_URL=postgresql://postgres:password@localhost:5432/the_citadel`

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | ✅ | — | Discord bot token |
| `DATABASE_URL` | ❌ | — | PostgreSQL connection string (Supabase) |
| `ENVIRONMENT` | ❌ | `development` | `development`, `staging`, or `production` |
| `LOG_LEVEL` | ❌ | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `OVERWATCH_ENABLED` | ❌ | `false` | Enable the Overwatch cog |
| `OVERWATCH_USER_ID` | ❌ | — | Your Discord user ID |
| `OVERWATCH_GUILD_ID` | ❌ | — | Your server ID |
| `GEMINI_API_KEY` | ❌ | — | Gemini API key (free at aistudio.google.com) |
| `GEMINI_MODEL` | ❌ | `gemini-2.0-flash` | Gemini model to use |
| `QUIET_HOURS_START` | ❌ | `01:00` | Start of quiet hours (HH:MM) |
| `QUIET_HOURS_END` | ❌ | `07:30` | End of quiet hours (HH:MM) |

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
│   ├── main.py              # Entry-point
│   ├── config.py            # Pydantic Settings configuration
│   ├── bot.py               # Bot factory and extension loader
│   ├── cogs/
│   │   ├── health.py        # /ping command
│   │   ├── admin_health.py  # /system-db-status command
│   │   ├── setup.py         # /setup command group
│   │   ├── onboarding.py    # /start + welcome messages
│   │   ├── profile.py       # Profile linking and viewing
│   │   ├── contests.py      # Contest syncing + /upcoming
│   │   ├── reminders.py     # Contest reminders
│   │   ├── events.py        # Event management commands
│   │   ├── lifecycle.py     # Background event lifecycle
│   │   ├── submissions.py   # Result submission + moderation
│   │   ├── leaderboard.py   # Leaderboard commands
│   │   ├── stats.py         # Statistics commands
│   │   ├── roles.py         # Role management
│   │   └── overwatch.py     # 🔒 Overwatch — personal productivity enforcer
│   ├── db/
│   │   ├── base.py          # SQLAlchemy declarative base
│   │   ├── engine.py        # Async engine and session factory
│   │   └── models.py        # ORM models (includes acc_* tables for Overwatch)
│   ├── services/
│   │   ├── overwatch.py     # Overwatch business logic
│   │   └── ...              # Other services
│   └── providers/
│       ├── gemini_client.py  # Gemini API provider (Overwatch)
│       └── codeforces.py     # Codeforces API client
├── overwatch_dashboard/
│   ├── main.py              # FastAPI dashboard
│   ├── templates/           # Jinja2 templates
│   └── static/              # CSS
├── migrations/
├── tests/
├── docs/
│   ├── README.md            # This file
│   ├── overwatch-setup.md   # Overwatch setup guide
│   ├── overwatch-roadmap.md # Overwatch roadmap
│   ├── discord-bot-setup.md # Developer setup guide
│   └── server-configuration.md
├── .env.example
├── alembic.ini
├── Dockerfile
└── pyproject.toml
```

## Discord Bot Setup

See [discord-bot-setup.md](discord-bot-setup.md) for detailed instructions.

Quick version:

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to **Bot** → **Reset Token** → copy the token
4. Enable **Server Members Intent** + **Message Content Intent** in the Bot tab
5. Go to **OAuth2 → URL Generator** → select `bot` + `applications.commands`
6. Select permissions: Send Messages, View Channels, Embed Links, Mention Everyone, Manage Channels
7. Invite the bot to your server with the generated URL
8. Paste the token into your `.env` file

## Server Configuration

See [server-configuration.md](server-configuration.md) for the full admin guide.

## License

MIT
