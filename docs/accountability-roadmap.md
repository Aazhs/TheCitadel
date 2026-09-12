# Accountability System — Roadmap & Open Decisions

This document tracks open design decisions, known limitations, and planned enhancements for the accountability cog. Items listed here are intentional tradeoffs made for the v0.2 prototype — not bugs.

---

## Open Decisions

### 1. Escalation Tier Mapping

**Current implementation:** Simple monotonic mapping in `providers/ollama_client.py`:
- 0 misses → `neutral`
- 1–2 misses → `strict`
- 3+ misses → `hostile`

**Open questions:**
- Should missed check-ins reset to 0 after the user replies, or decay gradually?
- Is there a hard ceiling (e.g. cap at 5 misses) or does it stay at `hostile` indefinitely?
- Should the escalation tier persist across bot restarts (currently it does via `UserContext.missed_checkins`)?
- Consider adding a `!reset-tone` command for manual override.

### 2. Priority Risk Scoring Formula

**Current implementation** (in `services/accountability.py`):
```
score = priority_weight + (overdue_hours × 0.5)
```
- Priority weights: Low=1, Medium=3, High=5
- Overdue hours: `max(0, (now - scheduled_time).total_hours)` — 0 if no `scheduled_time`

**Tuning opportunities:**
- Adjust the 0.5 overdue multiplier
- Add domain-based weighting
- Consider time-of-day preferences (e.g. harder tasks in the morning)
- Add recency bias (recently created tasks get a small boost)

### 3. `known_blockers` as Freeform Text

The `UserContext.known_blockers` field is currently a plain `Text` column. Consider structuring it into:
- Tags (e.g. `["waiting-on-review", "need-API-key"]`)
- A separate `Blockers` table with status tracking
- Integration with the LLM to detect when a blocker is mentioned in conversation

### 4. Model Hot-Swap

**Current:** Model is configured via `OLLAMA_MODEL` in `.env`. Changing it requires editing the file and restarting the bot.

**Future:** Add a `!model <name>` command for runtime hot-swap without restart. Verify the model exists via Ollama's API before switching.

---

## Known Limitations

### 5. No Auth on the Local Dashboard

The FastAPI dashboard at `accountability_dashboard/` has no authentication. It's designed for a trusted home network only.

**Future options:**
- Simple bearer token auth
- HTTP Basic Auth
- Bind to `127.0.0.1` only (simplest)

### 6. Manual "Done" Marking — Trust Boundary

When the user types `!done`, the task is marked complete with no verification. This is a deliberate self-honesty trust boundary, not a bug. The system can't verify whether you actually finished the work — it trusts you.

**Future:** Consider adding optional "proof of work" (e.g. paste a commit SHA or a screenshot) as an opt-in feature.

### 7. No Alembic Migration Chain for Local SQLite

The local SQLite database uses `create_all()` on startup instead of Alembic migrations. This is intentional for a single-user, single-file, local-only database.

**Revisit if:**
- Schema changes become frequent and you need rollback capability
- You start running multiple instances or sharing the DB file

### 8. No Test Coverage for New Modules

The new `cogs/accountability.py`, `services/accountability.py`, and `providers/ollama_client.py` have no unit tests yet. The existing repo's test conventions (`tests/`, `conftest.py` fixtures, pytest-asyncio) should be followed once this feature stabilises.

**Priority test targets:**
- `priority_risk_score()` — pure function, easy to test
- `is_quiet_hours()` — edge cases around midnight wrapping
- `escalation_tone()` — mapping correctness
- `parse_user_intent()` — mock the Ollama client, test JSON parsing + retry logic
- `determine_loop_state()` — state machine correctness

### 9. No Seed/Demo Data

The local SQLite database starts empty. Consider adding a `scripts/seed_accountability.py` script that populates a few sample tasks for initial testing.

---

## Planned Features (Not Yet Implemented)

- **Weekly summary DM** — Aggregate activity log into a weekly report sent every Sunday
- **Task categories/domains** — Group tasks by domain, show domain-level stats
- **Session history chart** — Visualise daily/weekly focus time in the dashboard
- **Blocker tracking** — Parse blockers from conversation, surface unresolved ones
- **Multiple users** — Extend beyond single-user (would need auth + per-user DB partitioning)
- **Mobile-friendly dashboard** — Responsive CSS for phone screens
- **Export** — CSV/JSON export of activity log and task history
