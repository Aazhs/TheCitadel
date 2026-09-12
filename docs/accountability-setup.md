# Accountability System Setup Guide

This guide covers setting up the **Accountability Cog** — a personal accountability system that creates a private channel on your server where the bot pings you on a 15-minute loop, demands progress updates, and escalates if you go dark. It uses a local Ollama LLM and a local SQLite database.

> [!NOTE]
> This feature is **fully local**. It does not use Supabase, does not affect the competitive-programming features, and the private channel is only visible to you and the bot.

---

## 1. Prerequisites

- A working Citadel bot installation (see [discord-bot-setup.md](discord-bot-setup.md))
- [Ollama](https://ollama.ai) installed locally
- Python 3.12+ with the project's dependencies installed
- The bot must be in the server where you want the private channel

---

## 2. Install & Pull Ollama Model

Install Ollama from [ollama.ai](https://ollama.ai), then pull the default model:

```bash
# Install Ollama (macOS)
brew install ollama

# Start the Ollama server
ollama serve

# Pull the default model (in a separate terminal)
ollama pull llama3.2:3b
```

Verify it's running:

```bash
curl http://localhost:11434/api/tags
```

You should see a JSON response listing available models.

---

## 3. Enable Message Content Intent

The accountability cog uses plain text messages (e.g. `!start auth module 45`) in the private channel, which requires the **Message Content Intent**.

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Select your application → **Bot** tab.
3. Scroll to **Privileged Gateway Intents**.
4. Enable the **Message Content Intent** toggle.
5. Click **Save Changes**.

> [!IMPORTANT]
> This is additive — enabling Message Content Intent does **not** change or break any existing slash command behavior. The cog only reads text in the private `#accountability-zone` channel.

---

## 4. Bot Permissions

The bot needs the **Manage Channels** permission in your server to create the private channel on first run. If you haven't already granted this, update the bot's role permissions in **Server Settings → Roles**.

The bot will create a channel called `#accountability-zone` with permission overwrites:
- `@everyone` — **denied** view access (nobody else can see it)
- **You** — can view and send messages
- **The bot** — can view, send, embed, and read history

---

## 5. Environment Variables

Add these to your `.env` file:

```bash
# Enable the accountability cog
ACCOUNTABILITY_ENABLED=true

# Your Discord user ID (right-click your name → Copy User ID)
ACCOUNTABILITY_USER_ID=123456789012345678

# The server (guild) where the private channel will be created
ACCOUNTABILITY_GUILD_ID=987654321098765432

# Local SQLite database path (gitignored by default — *.db is in .gitignore)
ACCOUNTABILITY_DB_PATH=./accountability.db

# Ollama configuration
OLLAMA_MODEL=llama3.2:3b
OLLAMA_HOST=http://localhost:11434

# Quiet hours — the bot won't ping you during this window
QUIET_HOURS_START=01:00
QUIET_HOURS_END=07:30
```

### Finding Your Discord User ID

1. Open Discord **Settings** → **Advanced** → Enable **Developer Mode**.
2. Right-click your username anywhere in Discord → **Copy User ID**.

### Finding Your Server (Guild) ID

1. With Developer Mode enabled, right-click the server name in the left sidebar.
2. Click **Copy Server ID**.

---

## 6. Running the Bot

Make sure Ollama is running first (`ollama serve`), then start the bot as usual:

```bash
python -m src.main
```

On startup, you should see these log lines:

```
Message Content Intent enabled (accountability cog)
Local SQLite database initialised at ./accountability.db
Loaded accountability cog (user: 123456789012345678, guild: 987654321098765432)
```

The first time the check-in loop runs, it will automatically create the `#accountability-zone` channel in your server. You'll see it appear in your channel list, visible only to you and the bot.

If Ollama is not running, the cog will be skipped gracefully:

```
Ollama not reachable at http://localhost:11434 — accountability cog will not start
Accountability cog failed to load — skipping
```

The rest of the bot's competitive-programming features will work normally regardless.

---

## 7. Running the Dashboard

The accountability dashboard is a separate FastAPI app:

```bash
# From the project root
ACCOUNTABILITY_DB_PATH=./accountability.db uvicorn accountability_dashboard.main:app --host 0.0.0.0 --port 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

The dashboard shows:
- **Active session** with a live-updating timer
- **Task queue** sorted by priority risk score, with inline editing
- **Activity log** showing all check-ins, escalations, and commands

> [!NOTE]
> The dashboard has no authentication for the prototype — it's intended for use on a trusted home network only.

---

## 8. Available Commands (in `#accountability-zone`)

Send these as plain messages in the private channel:

| Command | Description |
|---------|-------------|
| `!start <task> <minutes>` | Start a work session (e.g. `!start auth module 45`) |
| `!status` | Show current session status |
| `!pause` | Pause the active session |
| `!resume` | Resume the last paused session |
| `!done` | Mark the current task as complete |
| `!queue` | Show the task queue by priority risk |
| `!skip [task_id]` | Skip the top task or a specific task by ID |

---

## 9. How It Works

1. **Every 15 minutes** (outside quiet hours), the bot pings you in `#accountability-zone` asking for a progress update.
2. **If you have an active session**, it asks about that specific task.
3. **If you're idle**, it surfaces the highest-priority task from your queue.
4. **If you reply**, the LLM classifies your intent and responds accordingly.
5. **If you ignore it**, the missed check-in counter goes up and the tone escalates:
   - 0 misses → neutral
   - 1–2 misses → strict
   - 3+ misses → hostile (unfiltered, profanity included — by design)
6. **If a session goes overdue**, it keeps nagging on the same 15-minute cadence.

---

## 10. Disabling the Feature

Set `ACCOUNTABILITY_ENABLED=false` in your `.env` and restart the bot. The cog won't load, the `#accountability-zone` channel stays but goes silent. Delete the channel manually if you want it gone.
