# Discord Bot Setup Guide

This guide provides step-by-step instructions for developers setting up **The Citadel** — a competitive programming Discord bot. Follow these steps to register your bot application, configure privileged intents, grant appropriate permissions, generate an invite URL, configure role hierarchy, and set up your environment variables.

---

## 1. Creating the Bot Application

To host your own instance of The Citadel, you must first create an application in the Discord Developer Portal:

1. Navigate to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Log in with your Discord account credentials.
3. Click the **New Application** button in the top-right corner.
4. Enter `The Citadel` (or your preferred name) as the application name and agree to the Developer Terms of Service, then click **Create**.
5. In the left sidebar menu, navigate to the **Bot** tab.
6. Click **Reset Token** and confirm the prompt to generate a new bot token.
7. **Copy and store the token securely.** You will need this token for your `.env` configuration file.

> [!CAUTION]
> Treat your bot token like a password. Never commit your token to public version control repositories or share it publicly.

---

## 2. Enabling Privileged Intents

The Citadel requires specific Privileged Gateway Intents to detect when new members join a server:

1. On the **Bot** page in the Discord Developer Portal, scroll down to the **Privileged Gateway Intents** section.
2. Enable the **Server Members Intent** toggle.
   - **Why it's required:** Needed to trigger `on_member_join` events so the bot can send welcome messages to new members.
3. Keep the **Message Content Intent** toggle disabled.
   - **Note:** The Citadel uses native Discord Slash Commands exclusively, so Message Content Intent is **NOT** needed.

Click **Save Changes** at the bottom of the page before proceeding.

---

## 3. Required Bot Permissions

To operate properly across servers, The Citadel requires the following permissions:

| Permission | Purpose |
| :--- | :--- |
| **Send Messages** | Posts welcome messages, announcement updates, and contest reminders. |
| **View Channels** | Discovers and monitors configured channels within the server. |
| **Embed Links** | Sends rich, formatted embed messages for welcome guides and contest info. |
| **Mention Everyone** | Pings configured alert roles for contest notifications (optional but recommended). |
| **Use Application Commands** | Enables members to interact with slash commands (e.g., `/setup`, `/start`). |

---

## 4. OAuth2 URL Generation

Generate an invite URL to add The Citadel to your test or production Discord servers:

1. In the Discord Developer Portal, navigate to **OAuth2** > **URL Generator** in the left sidebar.
2. Under **Scopes**, select:
   - `bot`
   - `applications.commands`
3. Under **Bot Permissions**, select:
   - **View Channels** (`View Audit Log` / Text Permissions: `View Channels`)
   - **Send Messages**
   - **Embed Links**
   - **Mention Everyone**
   - **Use Application Commands**
4. Copy the generated URL from the bottom of the page.
5. Paste the URL into your web browser, select the server you wish to invite the bot to, and click **Authorize**.

---

## 5. Role Hierarchy Explanation

Discord enforces a strict **Role Hierarchy** system that governs bot capabilities regarding server roles:

- **Hierarchy Rule:** The Citadel can only mention, assign, or interact with roles that are positioned **BELOW** the bot's own highest role in the server's role list.
- **Alert Roles:** If server administrators configure a custom contest alert role, that role must be ordered below The Citadel's role in the server settings. Otherwise, the bot will be unable to mention the role when posting contest alerts.

### How to Adjust Role Hierarchy in Discord:

1. Open your Discord server and navigate to **Server Settings** > **Roles**.
2. Locate **The Citadel** role (or the role assigned to the bot).
3. Click and drag the bot's role so it is placed **above** any custom alert roles (such as `@Contest Alerts` or `@Competitive Programmer`).
4. Click **Save Changes**.

---

## 6. Environment Variables

The Citadel relies on environment variables for configuration. A template file named `.env.example` is included in the project root repository.

### Configuration Reference (`.env`):

```bash
# Required: Discord Bot Authentication Token
DISCORD_TOKEN=your-discord-bot-token-here

# Required: Database connection string (Supabase Postgres)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres

# Optional: Environment setting (development | production)
ENVIRONMENT=development

# Optional: Logging level (DEBUG | INFO | WARNING | ERROR | CRITICAL)
LOG_LEVEL=INFO
```

### Environment Variable Descriptions:

- **`DISCORD_TOKEN`** *(Required)*: The bot application token copied from the Discord Developer Portal.
- **`DATABASE_URL`** *(Required for full features)*: PostgreSQL database connection string (e.g., Supabase Postgres instance) used for persisting server configurations, user profiles, and contest data.
- **`ENVIRONMENT`** *(Optional)*: Specifies the application environment. Defaults to `development`.
- **`LOG_LEVEL`** *(Optional)*: Sets the verbosity of application logs. Defaults to `INFO`.
