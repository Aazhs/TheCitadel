# The Citadel — Incremental Build Prompts

Use these prompts **in order** in Antigravity. Each prompt is deliberately small so the agent can modify an existing repository instead of generating an expensive, oversized application all at once.

## Rules for every prompt

Paste this context at the end of **every** prompt:

> This is an existing repository. First inspect the current codebase and preserve working features. Make only the changes needed for this milestone. Do not rewrite unrelated files, add unnecessary services, or introduce a frontend/dashboard unless the prompt explicitly asks for it. Use Python 3.12, `discord.py`, Supabase Postgres, SQLAlchemy async, Alembic, `httpx`, Pydantic Settings, and pytest. Use slash commands. Never commit secrets. Before finishing, run or describe the exact lint/test commands and update the README only where needed.

---

## Prompt 0 — Repository foundation

```text
Create the initial repository for a Discord competitive-programming bot named `algorithm-arena-bot`.

Goal for this milestone: a minimal Discord bot can start locally, connect to Discord, register one `/ping` slash command, and read configuration safely. Do not build contest features, leaderboards, dashboard, Supabase models, or scheduled tasks yet.

Use:
- Python 3.12
- discord.py 2.x
- Pydantic Settings
- Ruff
- pytest
- Dockerfile
- `.env.example`

Create this structure:
- `src/main.py`
- `src/config.py`
- `src/bot.py`
- `src/cogs/health.py`
- `src/utils/logging.py`
- `tests/test_config.py`
- `pyproject.toml`
- `.env.example`
- `Dockerfile`
- `.gitignore`
- `README.md`

Requirements:
- `/ping` returns latency and a simple online message.
- Use structured, readable logging.
- Validate required environment variables at startup.
- Required environment variable: `DISCORD_TOKEN`.
- Include `ENVIRONMENT` and `LOG_LEVEL` with safe defaults.
- Do not hardcode any token, guild ID, role ID, or channel ID.
- Add clear local setup instructions to the README.
- Add a basic unit test for settings/configuration behavior.
- Configure Ruff and pytest in `pyproject.toml`.

At the end, provide the final file tree, exact commands to create a virtual environment, install dependencies, configure `.env`, and run the bot.

[paste the shared context here]
```

---

## Prompt 1 — Supabase/Postgres connection and migrations

```text
Add a persistent Supabase PostgreSQL database layer to the existing Algorithm Arena Discord bot. Do not add contest APIs or user commands beyond a small diagnostic command.

Use:
- SQLAlchemy 2.x async ORM
- asyncpg
- Alembic migrations
- Pydantic Settings

Add environment variable:
- `DATABASE_URL`

Create or update:
- async database engine/session management
- SQLAlchemy declarative base
- Alembic configuration and initial migration
- database health-check service
- `src/cogs/admin_health.py`
- tests using an isolated test strategy or mocks; do not require a live Supabase project in normal unit tests

Create only these initial tables:
1. `guild_settings`
   - id
   - discord_guild_id, unique
   - timezone, default `UTC`
   - onboarding_channel_id nullable
   - announcement_channel_id nullable
   - contest_alert_channel_id nullable
   - alert_role_id nullable
   - created_at, updated_at

2. `users`
   - id
   - discord_user_id, unique
   - created_at, updated_at

3. `guild_members`
   - id
   - guild_settings_id
   - user_id
   - verified_competitor boolean default false
   - created_at, updated_at
   - unique constraint on guild_settings_id + user_id

Implement `/system-db-status` as an admin-only, guild-only slash command. It should safely test database connectivity and return a concise ephemeral result. Do not expose secrets or connection strings.

Update README with Supabase setup, how to obtain a Postgres connection string, how to run migrations, and how to start locally.

[paste the shared context here]
```

---

## Prompt 2 — Server setup and onboarding

```text
Add server onboarding/configuration features to the existing Algorithm Arena bot.

Do not add Codeforces integration, contest scheduling, leaderboards, or a web dashboard yet.

Implement these admin-only, guild-only slash commands:
- `/setup onboarding-channel:#channel`
- `/setup announcement-channel:#channel`
- `/setup contest-alert-channel:#channel`
- `/setup alert-role:@role`
- `/setup view`

Persist the configured Discord IDs in `guild_settings`. Validate that the bot can view/send messages in selected channels. For the alert role, validate that the bot can mention it where allowed, but do not change Discord role membership yet.

Implement a `on_member_join` listener:
- Read the guild onboarding channel.
- If configured, post a friendly welcome message tagging the new member.
- Direct them to use `/start` and link their public coding profiles.
- If it is not configured, do nothing and log a warning only.

Implement member-facing `/start`:
- Guild-only.
- Ephemeral response.
- Explain the three next actions: link accounts, opt into contest alerts, and see upcoming events later.
- Do not falsely claim contest functions exist yet.

Implement `/setup reset` with a confirmation step suitable for Discord interactions. It should clear only Algorithm Arena guild configuration, not user profiles or event data.

Add tests for permission checks, configuration persistence, and safely missing configuration. Update documentation with required Discord permissions and role-hierarchy explanation.

[paste the shared context here]
```

---

## Prompt 3 — Link Codeforces accounts

```text
Add Codeforces account linking to the existing Algorithm Arena bot.

Implement a clean provider/service architecture. Use the official public Codeforces API through async `httpx`. All API calls must set a timeout and handle invalid handles, rate limits, temporary network failures, and malformed responses safely.

Add a `linked_accounts` database table through an Alembic migration:
- id
- guild_member_id
- platform enum/string; initially only `codeforces`
- handle
- normalized_handle
- profile_url
- validation_status
- current_rating nullable
- max_rating nullable
- global_rank nullable
- last_synced_at nullable
- last_sync_status nullable
- last_sync_error nullable
- created_at, updated_at
- unique guild_member_id + platform
- unique guild_member_id + normalized_handle is NOT required; different users may have different constraints, but prevent the same handle being linked by multiple members in the same guild unless an admin later resolves it.

Implement:
- `/link-codeforces handle:<string>`
- `/unlink platform:codeforces`
- `/my-profile`
- `/profile member:@user` 

Behavior:
- Validate Codeforces handle before saving.
- Fetch current rating, max rating, and rank where available.
- Store only public profile information.
- Use ephemeral responses for `/link-codeforces`, `/unlink`, and `/my-profile`.
- `/profile` may be public but must show only safe public information.
- Update `verified_competitor=true` when a member has at least one validated account.
- Do not add CodeChef or LeetCode yet.
- Include a per-user cooldown for manual linking attempts to reduce API abuse.

Add provider unit tests using mocked Codeforces API responses. Add tests for invalid handles, duplicate links, relinking, and database persistence. Update README and command documentation.

[paste the shared context here]
```

---

## Prompt 4 — Codeforces contest discovery and `/upcoming`

```text
Add Codeforces contest discovery to the existing Algorithm Arena bot. Do not build automatic reminders or event creation yet.

Use the existing Codeforces provider architecture and official public contest-list API.

Create an Alembic migration and `contests` table:
- id
- platform
- external_contest_id
- name
- url
- start_time_utc
- duration_seconds nullable
- phase/status
- created_at, updated_at
- unique constraint platform + external_contest_id

Implement a contest sync service:
- Fetch and normalize upcoming Codeforces contests.
- Upsert them in the database.
- All datetimes timezone-aware and stored in UTC.
- Safe timeout/retry behavior for transient failures.
- Do not send any Discord notification in this milestone.

Implement commands:
- `/upcoming` — show the next 5 upcoming Codeforces contests in a Discord embed.
- `/refresh-codeforces-contests` — admin-only; triggers a sync and responds with concise summary.

Embed should include contest name, Discord-native time formatting, duration if present, and official contest link.

Add a small scheduled job that refreshes the contest database every 6 hours, but ensure it starts only once and does not duplicate after reconnects. Log job success/failure.

Include tests for normalization, database upsert behavior, empty upcoming-contest results, and command formatting. Update documentation.

[paste the shared context here]
```

---

## Prompt 5 — Automated contest notifications

```text
Add automatic Codeforces contest reminders to the existing Algorithm Arena bot. Use contest data already stored in the database. Do not add custom events, result submission, or leaderboards yet.

Create an Alembic migration and `notification_deliveries` table:
- id
- guild_settings_id
- contest_id
- notification_type (`24h`, `1h`, `10m`)
- scheduled_for_utc
- sent_at nullable
- status
- discord_message_id nullable
- error_message nullable
- unique constraint guild_settings_id + contest_id + notification_type

Requirements:
- Run a reliable periodic reminder job every few minutes.
- Default reminders: 24 hours, 1 hour, and 10 minutes before a contest.
- Send to configured `contest_alert_channel_id` only if reminders are enabled.
- Mention configured alert role only if set; never ping `@everyone`.
- Use a clean rich embed with contest title, platform, start time, duration, URL, and reminder wording.
- No duplicate notification, including after bot restart.
- Missing/deleted channel, missing role, or Discord permission failure must create a useful log and update delivery status without crashing the job.

Add fields to `guild_settings` if needed:
- reminders_enabled default true

Implement commands:
- `/reminders status`
- `/reminders enable` — admin only
- `/reminders disable` — admin only
- `/reminders test` — admin only; posts a test embed to the configured alert channel

Add thorough tests for time-window logic, duplicate prevention, disabled reminders, and missing configuration. Update operations/troubleshooting documentation.

[paste the shared context here]
```

---

## Prompt 6 — Custom weekly events and registration

```text
Add admin-created weekly coding events to the existing Algorithm Arena bot. This milestone is for creating, announcing, registering for, and tracking events. Do not add final result submissions or leaderboards yet.

An event can represent:
- Codeforces official contest
- CodeChef official contest
- LeetCode contest/watch event
- Custom practice contest
- Daily LeetCode problem

Create an Alembic migration with these tables:

`events`:
- id UUID or suitable ID
- guild_settings_id
- title
- event_type
- platform nullable
- status (`draft`, `published`, `registration_open`, `active`, `ended`, `cancelled`)
- description
- official_url nullable
- start_time_utc
- end_time_utc
- registration_deadline_utc nullable
- announcement_channel_id nullable
- discussion_channel_id nullable
- results_channel_id nullable
- announcement_message_id nullable
- created_by_discord_user_id
- created_at, updated_at

`event_registrations`:
- id
- event_id
- guild_member_id
- status
- registered_at
- unique event_id + guild_member_id

Implement admin-only commands:
- `/event-create` with title, type, platform optional, official URL optional, start time, end time, description, announcement channel, discussion channel, results channel
- `/event-publish event_id:<id>`
- `/event-cancel event_id:<id>`
- `/event-list`
- `/event-view event_id:<id>`

Implement member command:
- `/register event_id:<id>`
- `/my-events`

Publishing behavior:
- Post a rich embed to the configured event announcement channel.
- Include a Discord button labelled `Register`.
- Button registers the member and gives an ephemeral confirmation.
- Require a linked Codeforces account only for Codeforces events; make this validation configurable and do not block unrelated event types.
- If configured discussion channel exists, post a discussion starter message/thread. Do not enable spoilers/moderation automation yet.

Use server-side state checks: do not allow registration after deadline or for cancelled events. Add tests for event state, registration constraints, button interaction, and database queries. Update admin documentation.

[paste the shared context here]
```

---

## Prompt 7 — Event lifecycle and result submission

```text
Add event lifecycle automation and result collection to the existing Algorithm Arena bot. Do not build scoring/leaderboards in this milestone.

Extend event statuses to include:
- `active`
- `ended`
- `submission_open`
- `finalized`

Add event fields if needed:
- submission_deadline_utc
- results_require_moderator_approval boolean default true

Create `event_submissions` through Alembic:
- id
- event_id
- guild_member_id
- questions_solved integer
- claimed_rank nullable
- claimed_rating_before nullable
- claimed_rating_after nullable
- claimed_rating_change nullable
- evidence_url nullable
- reflection nullable
- verification_status (`pending`, `verified`, `rejected`, `adjusted`)
- submitted_at
- updated_at
- verified_by_discord_user_id nullable
- verified_at nullable
- moderator_note nullable
- unique event_id + guild_member_id

Build periodic lifecycle job:
- At event start: mark active and post “The Arena is Open” in configured discussion channel.
- At event end: mark ended/submission_open and post “Contest Ended — Submit Your Results” in results channel.
- Include a `Submit Results` Discord button.
- At submission deadline: close submissions and prevent new/updated entries.

Button behavior:
- Open a Discord modal.
- Fields: questions solved (required), claimed rank optional, rating before optional, rating after optional, evidence URL optional, short reflection optional.
- Validate integers, URLs, event state, registration requirement if enabled, and deadline.
- Allow member to replace their own result before the deadline.
- New submissions default to `pending` if approval is required, otherwise `verified`.
- Send only an ephemeral confirmation to submitter.

Implement admin commands:
- `/submission-list event_id:<id> status:<optional>`
- `/submission-approve submission_id:<id> note:<optional>`
- `/submission-reject submission_id:<id> reason:<required>`

All moderator actions must be logged. Add an `audit_logs` table if one does not exist.

Important integrity rule: do not claim self-reported ranking, rating, or questions solved are verified. Label pending/self-reported information clearly.

Add tests for lifecycle timing, modal input validation, deadline enforcement, updates before deadline, approval/rejection, and audit logs. Update documentation.

[paste the shared context here]
```

---

## Prompt 8 — Per-event points and leaderboard

```text
Add transparent scoring and per-event leaderboards to the existing Algorithm Arena bot.

Use only event submissions that are `verified` or `adjusted` by default. Pending submissions may be shown to admins but must not affect official leaderboard until verified.

Add fields/migrations:
- `events.points_config` JSONB with a scoring snapshot
- `event_submissions.points_awarded`
- `event_submissions.score_breakdown` JSONB
- `event_leaderboard_entries` table: event_id, guild_member_id, rank, total_points, score_breakdown, is_final, computed_at, unique event_id + guild_member_id

Implement default scoring configuration:
- 100 points for verified participation
- 100 points per question solved
- Positive claimed/verified rating gain × 2 points, only if moderator approved or reliably API-derived
- Optional rank bonus configuration; disabled by default unless rank is trustworthy
- Tie-break in order: more questions solved, greater verified rating gain, earlier submission timestamp, stable Discord user ID

Requirements:
- Admin can configure event scoring before finalization using `/event-set-scoring` with a safe, limited interface. Do not require free-form JSON from Discord if avoidable.
- Compute a full score breakdown for every entry.
- Recompute standings whenever a moderator approves/rejects/adjusts a submission.
- `/event-leaderboard event_id:<id>` displays top 10 in an embed and shows verification state appropriately.
- `/event-leaderboard-post event_id:<id>` admin-only posts leaderboard in the event results channel.
- `/event-finalize event_id:<id>` admin-only closes result changes, computes final leaderboard, marks entries final, and posts the final embed.
- Do not permit finalization while submissions are still open unless admin explicitly confirms.

Include an example leaderboard embed:
1. @Aarav — 400 points — 3 solved
2. @Meera — 300 points — 2 solved

Add extensive unit tests for scoring, all tie-break levels, pending submission exclusion, recomputation, finalization, and score breakdown persistence. Update scoring documentation.

[paste the shared context here]
```

---

## Prompt 9 — Overall leaderboard and roles

```text
Add server-wide overall leaderboards and achievement roles to the existing Algorithm Arena bot.

Create or extend `guild_members` with:
- arena_points_all_time
- arena_points_monthly
- arena_points_weekly
- events_participated
- verified_results_count
- problems_solved_total
- current_streak
- longest_streak
- updated_at

Create `role_mappings` table:
- id
- guild_settings_id
- category (`rating`, `achievement`, `champion`)
- min_value nullable
- role_id
- role_name_cache nullable
- created_at, updated_at

Implement aggregation:
- Update member overall statistics whenever an event leaderboard is finalized.
- Make the update idempotent; finalizing same event twice must not double-count points.
- Weekly and monthly periods should use guild timezone, default UTC.

Implement member commands:
- `/leaderboard scope:<weekly|monthly|all-time> metric:<arena-points|participation|problems-solved|codeforces-rating>`
- `/rank`
- `/my-stats`

Implement achievement roles:
- `Verified Competitor`: assigned when at least one account is validated.
- `Contest Regular`: configurable threshold based on event participation.
- `Weekly Champion`: top weekly Arena points.
- `Arena Champion`: top monthly Arena points.

Implement Codeforces rating roles based on stored current rating:
- Unrated
- Newbie below 1200
- Pupil 1200–1399
- Specialist 1400–1599
- Expert 1600–1899
- Candidate Master+ 1900+

Implement admin commands:
- `/role-map-view`
- `/role-map-set category:<...> min_value:<optional> role:@role`
- `/role-map-reset-defaults`
- `/sync-roles`

Safety requirements:
- Bot must only add/remove roles configured as Algorithm Arena-managed roles.
- Never remove unrelated roles.
- Gracefully report missing/manageability/role hierarchy issues.
- Document required Discord permissions and bot-role ordering.

Add tests for aggregation idempotency, ranking, weekly/monthly period boundaries, rating-role selection, achievement roles, and safe role removal.

[paste the shared context here]
```

---

## Prompt 10 — Daily LeetCode problems

```text
Add daily LeetCode problem events to the existing Algorithm Arena bot. Do not use brittle or unauthorized scraping. V1 must support admin-scheduled public LeetCode problem URLs and self-reported/moderator-verified completion.

Build this using the existing events and event_problems system. Add `event_problems` if absent:
- id
- event_id
- platform
- title
- url
- difficulty nullable
- tags JSONB nullable
- point_value
- first_solve_bonus
- ordering
- created_at

Implement admin command:
- `/daily-problem-create title:<string> url:<url> difficulty:<easy|medium|hard> publish_time:<ISO datetime or date/time> deadline:<ISO datetime> points:<int>`

Implement automatic behavior:
- At publish time, create/publish a daily-problem event and post a rich embed in the configured announcement or daily-problem channel.
- Embed includes title, difficulty, URL, deadline, points, and a `Mark Complete` button.
- Create a discussion thread or post a discussion prompt in configured discussion channel.
- At deadline, close completion submissions and post a daily leaderboard.

`Mark Complete` button:
- Opens modal requesting optional public evidence URL and optional reflection.
- Uses completion timestamp from server.
- Defaults to pending verification when required by guild settings.

Scoring defaults:
- Easy: 50 points
- Medium: 100 points
- Hard: 175 points
- First verified completion: 50 bonus points

Implement `/daily-leaderboard` and include daily completions in all-time/weekly/monthly points only after verification/finalization.

Document clearly that LeetCode V1 completion verification is limited and public/profile/evidence based; never label it automatically verified unless a reliable provider is later implemented. Add tests.

[paste the shared context here]
```

---

## Prompt 11 — CodeChef and LeetCode profile linking

```text
Add CodeChef and LeetCode profile linking to the existing Algorithm Arena bot, using the existing linked_accounts table and `/link` flow.

Implement unified command:
- `/link platform:<codeforces|codechef|leetcode> profile:<url_or_handle>`

Keep `/link-codeforces` as a backward-compatible alias if it already exists.

Rules:
- Codeforces: retain official API validation and rating sync.
- CodeChef: accept profile URL/handle, normalize it, validate only through a stable and appropriate public source. If no reliable source is available, store as `pending_manual_validation` or `unverified`; never falsely claim automatic verification.
- LeetCode: accept profile URL/username, normalize it, and store as unverified/manual-validation in V1 unless a reliable approved source is configured.
- `/my-profile` must show all linked platforms, validation status, and last-sync date.
- `/unlink` supports all platforms.

Create provider interfaces for CodeChef and LeetCode that make later integrations easy. Do not introduce brittle scrapers. Include feature flags/configuration for optional future verification providers.

Update user privacy documentation and add tests for parsing URLs/handles, platform-specific validation status, duplicate prevention, and unlinking.

[paste the shared context here]
```

---

## Prompt 12 — Minimal admin dashboard (only after bot works)

```text
The Discord bot is now functional. Add a minimal web admin dashboard, but do not rewrite bot functionality or duplicate business logic unnecessarily.

Use:
- Next.js 14+ App Router
- TypeScript
- Tailwind CSS
- Supabase Auth
- Discord OAuth login
- Supabase Postgres

Build only these dashboard capabilities for V1:
1. Secure admin sign-in with Discord OAuth.
2. Server/guild selection for configured administrators.
3. Upcoming events list.
4. Create/edit/publish/cancel event form.
5. Event submission moderation queue with approve/reject actions and mandatory reason for rejection.
6. Event leaderboard view.
7. Basic settings: timezone, configured channel IDs, alert role ID, reminder enable/disable.

Authorization:
- Do not rely on client-side checks alone.
- Use a server-side allowlist / `guild_admins` table initially.
- Document how Discord role-based authorization can be added safely later.
- Never expose Supabase service-role key in browser code.

Design requirements:
- Clean, simple, responsive UI.
- No analytics, charts, billing, marketing site, or unnecessary pages.
- Show clear loading, empty, success, and error states.
- Use validation for all forms.

Deploy dashboard as a Render Web Service. Keep Discord bot as its existing Render Background Worker. Add Dockerfile, environment-variable docs, and GitHub Actions checks for the dashboard.

Add a concise `docs/dashboard.md` with local run and Render deployment instructions. Add tests for admin access and form validation.

[paste the shared context here]
```

---

## Prompt 13 — Production hardening and deployment

```text
Review the complete existing Algorithm Arena repository and make it ready for a small real college-server launch on Render + Supabase. Do not add major new product features.

Perform a practical production-hardening pass:
- Audit environment variable handling and remove any accidental secrets/default credentials.
- Add or improve structured logs.
- Add global Discord command and interaction error handling.
- Ensure scheduled jobs do not duplicate after reconnect/redeploy.
- Ensure notification and leaderboard operations are idempotent.
- Add API timeouts, bounded retries, and rate-limit-safe behavior.
- Improve database transaction boundaries and error recovery.
- Ensure startup performs safe database checks and logs migration expectations.
- Add a `/system-status` admin command with non-sensitive status: database reachable, jobs running, last successful contest sync, bot latency.
- Add a basic health endpoint only if it fits the deployment architecture.
- Verify Discord permissions/role hierarchy errors are clearly actionable.
- Improve test coverage for high-risk flows.
- Add GitHub Actions CI for Python linting/tests and dashboard lint/build/tests if dashboard exists.
- Add `render.yaml` or exact Render configuration for bot background worker and dashboard web service.
- Write final deployment runbook: Supabase setup, migrations, Render services, variables, Discord developer portal, initial server setup, backup/export, rollback, and troubleshooting.

Create a final `LAUNCH_CHECKLIST.md` covering:
- Discord bot token configured
- OAuth redirect URLs configured
- Supabase migration applied
- Render services deployed
- channel and roles configured
- bot role hierarchy correct
- `/system-status` successful
- test contest created
- test reminder received
- test result submitted/moderated
- event leaderboard finalized
- overall leaderboard checked
- privacy command verified

Do not change user-facing scoring rules or add unrequested features. Focus on reliability, documentation, and safe deployment.

[paste the shared context here]
```

---

# Suggested build sequence

1. Complete Prompts 0–5 before inviting anybody.
2. Test with a private Discord server and 3–5 friends.
3. Complete Prompts 6–9 before running the first real weekly contest.
4. Add Prompt 10 only after the contest workflow is stable.
5. Build the dashboard in Prompt 12 only if Discord admin commands become painful.
6. Run Prompt 13 immediately before public launch.

# Minimum viable launch

You can launch with these features alone:

- Codeforces profile linking
- `/upcoming`
- Automatic contest reminders
- Admin-created event
- Participant registration
- Result modal
- Moderator approval
- Event leaderboard

Everything else is an upgrade.