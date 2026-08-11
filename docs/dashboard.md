# Algorithm Arena Web Dashboard

This document outlines the setup and deployment of the Next.js 14 Web Dashboard for Algorithm Arena.

## Prerequisites & Setup

### 1. Supabase Setup
The dashboard uses Supabase Auth alongside your existing Supabase Postgres database.
1. Go to your Supabase project dashboard.
2. Navigate to **Authentication** > **Providers** and enable **Discord**.
3. You will need a **Client ID** and **Client Secret** from the Discord Developer Portal.
4. Set the **Redirect URI** in the Discord Developer Portal to your Supabase OAuth redirect URL (e.g., `https://<project-ref>.supabase.co/auth/v1/callback`).

### 2. Discord Developer Portal
1. Go to [Discord Developer Portal](https://discord.com/developers/applications).
2. Select your application.
3. Under **OAuth2**, add the Redirect URI from Supabase.
4. Copy the Client ID and Client Secret to your Supabase Auth settings.

### 3. Environment Variables
You need to provide the following environment variables to the Next.js dashboard:

```env
# URL and Anon Key for public Supabase access
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>

# Service Role Key for server-side admin operations (DO NOT EXPOSE TO CLIENT)
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>

# Database URL for direct postgres connections if needed (used by backend)
DATABASE_URL=postgresql://postgres:...
```

## Running Locally

1. Navigate to the `dashboard` directory:
   ```bash
   cd dashboard
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Access the dashboard at `http://localhost:3000`.

## Initializing Admin Access

Because this is a secure dashboard, you must explicitly whitelist Discord users as admins before they can log in and manage servers.

Use the provided Python script in the root of the repo:
```bash
python scripts/add_admin.py <GUILD_ID> <YOUR_DISCORD_USER_ID>
```
This will add you to the `guild_admins` table for that specific guild.

## Deploying to Render

The dashboard is designed to run as a **Web Service** on Render, alongside your existing Background Worker (the bot).

1. Go to your Render Dashboard and create a new **Web Service**.
2. Connect this GitHub repository.
3. Use the following configuration:
   - **Root Directory**: `dashboard` (or leave blank if using Dockerfile at root, but since we put the Dockerfile in `dashboard/`, set it to `dashboard`).
   - **Environment**: Docker
   - **Branch**: main
4. Set the environment variables in the Render dashboard (see section 3 above).
5. Click **Create Web Service**. Render will build the Docker container using `dashboard/Dockerfile` and deploy it.

## Architecture Notes
- Authorization is strictly enforced server-side. The dashboard checks the `guild_admins` table before allowing any actions or viewing data for a specific guild.
- The UI is built using Next.js 14 App Router, Server Actions, and Tailwind CSS.
- Since Alembic manages the database schema via Python, the Next.js application connects to Postgres strictly for data manipulation, bypassing Row Level Security via the `SUPABASE_SERVICE_ROLE_KEY` (since it's an admin-only portal).
