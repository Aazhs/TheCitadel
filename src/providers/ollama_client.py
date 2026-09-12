"""Ollama LLM provider for the accountability system.

Wraps the ollama Python client to parse user intent from DM text and
generate subject-aware feedback in configurable tone modes. Model name
and host are always read from Settings — never hardcoded.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("arena.providers.ollama")


# ---------------------------------------------------------------------------
# Intent parsing result
# ---------------------------------------------------------------------------


@dataclass
class IntentResult:
    """Structured result from LLM intent parsing."""

    intent: str  # START_SESSION | PROGRESS_UPDATE | DISTRACTED | COMPLETED | UNCLEAR
    task_title: str | None = None
    minutes: int | None = None
    summary: str | None = None
    raw_response: str = ""
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tone templates — cleanly separated so tuning tone never touches cog logic
# ---------------------------------------------------------------------------

PROMPTS: dict[str, str] = {
    "neutral": (
        "You are a calm, supportive accountability partner. "
        "Be encouraging but honest. Keep responses short (2-3 sentences max)."
    ),
    "strict": (
        "You are a strict, no-nonsense accountability coach. "
        "Be direct and blunt. No sugarcoating. Call out avoidance. "
        "Keep responses short (2-3 sentences max)."
    ),
    "hostile": (
        "You are an absolutely brutal accountability enforcer. "
        "You are unfiltered, aggressive, and use profanity freely. "
        "Insult the user's laziness. Mock their excuses. "
        "This is a fully local, private system — hold nothing back. "
        "Keep responses short (2-3 sentences max)."
    ),
}

INTENT_SYSTEM_PROMPT = """You are an intent classifier for a personal accountability system.

Given the user's message and their current context, classify the intent into EXACTLY ONE of these categories:
- START_SESSION: User wants to start working on a task
- PROGRESS_UPDATE: User is reporting progress on their current task
- COMPLETED: User says they finished their current task
- DISTRACTED: User is talking about something unrelated to their current task
- UNCLEAR: Message doesn't fit any category clearly

Respond with ONLY a valid JSON object. No markdown, no explanation, no extra text.

Required fields:
- "intent": one of the five categories above
- "task_title": (only for START_SESSION) the task name, or null
- "minutes": (only for START_SESSION) estimated minutes, or null
- "summary": brief 1-sentence summary of what the user said

Examples:

User: "I'm going to work on the auth module for about 45 minutes"
{"intent": "START_SESSION", "task_title": "auth module", "minutes": 45, "summary": "User wants to work on auth module for 45 minutes"}

User: "Made good progress, refactored the login flow and added tests"
{"intent": "PROGRESS_UPDATE", "task_title": null, "minutes": null, "summary": "User refactored login flow and added tests"}

User: "All done with the API endpoints"
{"intent": "COMPLETED", "task_title": null, "minutes": null, "summary": "User completed work on API endpoints"}

User: "Did you see that new Marvel trailer?"
{"intent": "DISTRACTED", "task_title": null, "minutes": null, "summary": "User is talking about a movie trailer"}

User: "hmm not sure"
{"intent": "UNCLEAR", "task_title": null, "minutes": null, "summary": "Ambiguous response"}
"""

RETRY_PROMPT = (
    "Your previous response was not valid JSON. "
    "Return ONLY the JSON object with the fields: intent, task_title, minutes, summary. "
    "No markdown, no code fences, no explanation."
)


# ---------------------------------------------------------------------------
# Escalation tone mapping
# ---------------------------------------------------------------------------


def escalation_tone(missed_count: int) -> str:
    """Map missed check-in count to a tone mode.

    Simple monotonic mapping — exact thresholds are flagged as tunable
    in docs/accountability-roadmap.md.

    Args:
        missed_count: Number of consecutive missed check-ins.

    Returns:
        One of 'neutral', 'strict', or 'hostile'.
    """
    if missed_count <= 0:
        return "neutral"
    if missed_count <= 2:
        return "strict"
    return "hostile"


# ---------------------------------------------------------------------------
# Ollama reachability check
# ---------------------------------------------------------------------------


async def check_ollama_reachable(host: str) -> bool:
    """Quick reachability check against the Ollama API.

    Args:
        host: Ollama API base URL (e.g. 'http://localhost:11434').

    Returns:
        True if Ollama responds, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{host}/api/tags")
            response.raise_for_status()
            logger.info("Ollama reachable at %s", host)
            return True
    except httpx.HTTPStatusError as e:
        logger.warning("Ollama HTTP error at %s: %s", host, e)
        return False
    except httpx.RequestError as e:
        logger.warning("Ollama unreachable at %s: %s", host, e)
        return False
    except Exception as e:
        logger.warning("Unexpected error checking Ollama at %s: %s", host, e)
        return False


# ---------------------------------------------------------------------------
# Core: intent parsing
# ---------------------------------------------------------------------------


def _build_context_string(
    session_context: dict | None = None,
    user_context: dict | None = None,
) -> str:
    """Build a context string for the LLM from session and user context."""
    parts = []
    if user_context:
        if user_context.get("current_topic"):
            parts.append(f"Current topic: {user_context['current_topic']}")
        if user_context.get("subject_name"):
            parts.append(f"Subject: {user_context['subject_name']}")
        if user_context.get("known_blockers"):
            parts.append(f"Known blockers: {user_context['known_blockers']}")
    if session_context:
        if session_context.get("task_title"):
            parts.append(f"Active task: {session_context['task_title']}")
        if session_context.get("minutes_remaining") is not None:
            parts.append(f"Minutes remaining: {session_context['minutes_remaining']}")

    return "\n".join(parts) if parts else "No active session or context."


def _parse_json_response(text: str) -> dict | None:
    """Attempt to extract a JSON object from LLM output."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


async def parse_user_intent(
    text: str,
    session_context: dict | None = None,
    user_context: dict | None = None,
    *,
    model: str = "llama3.2:3b",
    host: str = "http://localhost:11434",
) -> IntentResult:
    """Parse user intent from a DM message using Ollama.

    On parse failure, retries once with a stricter prompt. If still invalid,
    returns UNCLEAR and the caller should ask the user to rephrase.

    Args:
        text: The user's raw DM message.
        session_context: Dict with active session info (task_title, minutes_remaining).
        user_context: Dict with user context (current_topic, subject_name, known_blockers).
        model: Ollama model name.
        host: Ollama API host.

    Returns:
        IntentResult with the classified intent.
    """
    import ollama as ollama_lib

    context_str = _build_context_string(session_context, user_context)
    user_message = f"Context:\n{context_str}\n\nUser message: {text}"

    client = ollama_lib.AsyncClient(host=host)

    # First attempt
    try:
        response = await client.chat(
            model=model,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            options={"temperature": 0.1},
        )
        raw = response["message"]["content"]
        parsed = _parse_json_response(raw)

        if parsed and "intent" in parsed:
            return IntentResult(
                intent=parsed["intent"],
                task_title=parsed.get("task_title"),
                minutes=parsed.get("minutes"),
                summary=parsed.get("summary"),
                raw_response=raw,
                extra={k: v for k, v in parsed.items() if k not in ("intent", "task_title", "minutes", "summary")},
            )

        # Retry with stricter prompt
        logger.warning("First intent parse failed, retrying with stricter prompt")
        response = await client.chat(
            model=model,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": RETRY_PROMPT},
            ],
            options={"temperature": 0.0},
        )
        raw_retry = response["message"]["content"]
        parsed_retry = _parse_json_response(raw_retry)

        if parsed_retry and "intent" in parsed_retry:
            return IntentResult(
                intent=parsed_retry["intent"],
                task_title=parsed_retry.get("task_title"),
                minutes=parsed_retry.get("minutes"),
                summary=parsed_retry.get("summary"),
                raw_response=raw_retry,
            )

        # Both attempts failed
        logger.error("Intent parsing failed after retry. Raw: %s | Retry: %s", raw, raw_retry)
        return IntentResult(intent="UNCLEAR", raw_response=raw_retry)

    except Exception as e:
        logger.exception("Ollama intent parsing error: %s", e)
        return IntentResult(intent="UNCLEAR", raw_response=str(e))


# ---------------------------------------------------------------------------
# Core: feedback generation
# ---------------------------------------------------------------------------


async def generate_feedback(
    intent: str,
    context: str,
    tone: str = "strict",
    *,
    model: str = "llama3.2:3b",
    host: str = "http://localhost:11434",
) -> str:
    """Generate a feedback message for the user in the specified tone.

    Args:
        intent: The classified intent (e.g. 'PROGRESS_UPDATE', 'DISTRACTED').
        context: Human-readable context about the current session/task.
        tone: One of 'neutral', 'strict', 'hostile'.
        model: Ollama model name.
        host: Ollama API host.

    Returns:
        A short feedback string for the Discord DM.
    """
    import ollama as ollama_lib

    tone_prompt = PROMPTS.get(tone, PROMPTS["strict"])

    intent_instructions = {
        "PROGRESS_UPDATE": "The user just gave you a progress update. Acknowledge it and push them to keep going.",
        "DISTRACTED": "The user is off-topic and not working on their task. Call them out and redirect.",
        "COMPLETED": "The user finished their task. Acknowledge the win briefly.",
        "START_SESSION": "The user is starting a new work session. Confirm and set expectations.",
        "UNCLEAR": "The user's message was unclear. Ask them to be specific about what they're working on.",
    }

    instruction = intent_instructions.get(intent, intent_instructions["UNCLEAR"])

    client = ollama_lib.AsyncClient(host=host)

    try:
        response = await client.chat(
            model=model,
            messages=[
                {"role": "system", "content": f"{tone_prompt}\n\n{instruction}"},
                {"role": "user", "content": f"Context: {context}"},
            ],
            options={"temperature": 0.7},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        logger.exception("Ollama feedback generation error: %s", e)
        # Fallback — never leave the user hanging with no response
        fallbacks = {
            "PROGRESS_UPDATE": "Got it. Keep pushing.",
            "DISTRACTED": "Focus. Get back to work.",
            "COMPLETED": "Done. What's next?",
            "START_SESSION": "Session started. Go.",
            "UNCLEAR": "What are you working on? Be specific.",
        }
        return fallbacks.get(intent, "What are you doing? Be specific.")
