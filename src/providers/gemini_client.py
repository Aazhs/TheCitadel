"""Gemini LLM provider for the overwatch system.

Uses the Gemini API (free tier) for intent parsing and feedback generation.
Replaces the previous local Ollama provider.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("arena.providers.gemini")

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
# Tone templates
# ---------------------------------------------------------------------------

PROMPTS: dict[str, str] = {
    "neutral": (
        "You are a calm, supportive overwatch partner. "
        "Be encouraging but honest. Keep responses short (2-3 sentences max)."
    ),
    "strict": (
        "You are a strict, no-nonsense overwatch coach. "
        "Be direct and blunt. No sugarcoating. Call out avoidance. "
        "Keep responses short (2-3 sentences max)."
    ),
    "hostile": (
        "You are an absolutely brutal overwatch enforcer. "
        "You are unfiltered, aggressive, and use profanity freely. "
        "Insult the user's laziness. Mock their excuses. "
        "This is a fully private system — hold nothing back. "
        "Keep responses short (2-3 sentences max)."
    ),
}

INTENT_SYSTEM_PROMPT = """You are an intent classifier for a personal overwatch system. You MUST be precise.

Given the user's message and context, classify the intent into EXACTLY ONE category:

1. COMPLETED — User explicitly says the task is FINISHED, DONE, or COMPLETE. They must use past-tense or definitive completion language.
   YES: "all done", "finished it", "task is complete", "wrapped it up", "done with it"
   NO: "doing it", "working on it", "making progress", "almost done", "nearly there"

2. PROGRESS_UPDATE — User is reporting they ARE CURRENTLY working on something or have made partial progress. This is the DEFAULT when someone describes ongoing work.
   YES: "doing it", "working on it", "made some progress", "halfway through", "still going", "on it"
   NO: "finished it", "all done", "completed"

3. START_SESSION — User explicitly wants to BEGIN a NEW task. Must mention starting something new.
   YES: "going to work on X", "starting X", "let me do X for 30 min"
   NO: "working on X" (already working = PROGRESS_UPDATE)

4. DISTRACTED — User is talking about something completely unrelated to any work task.
   YES: "did you see that movie", "what's for dinner", random chitchat
   NO: "I'm stuck on a bug" (that's work = PROGRESS_UPDATE)

5. UNCLEAR — Message is too short or ambiguous to classify with confidence.
   YES: "hmm", "ok", "maybe", single emoji
   NO: "doing it" (that's clearly PROGRESS_UPDATE)

CRITICAL RULES:
- "doing it", "on it", "yeah working on it" = PROGRESS_UPDATE, NEVER COMPLETED
- COMPLETED requires EXPLICIT completion language (done, finished, complete, wrapped up)
- When in doubt between COMPLETED and PROGRESS_UPDATE, ALWAYS choose PROGRESS_UPDATE
- When in doubt between any category and UNCLEAR, choose the more specific one

Respond with ONLY valid JSON. No markdown, no explanation.

Required fields:
- "intent": one of the five categories
- "task_title": (only for START_SESSION) the task name, or null
- "minutes": (only for START_SESSION) estimated minutes, or null
- "summary": brief 1-sentence summary of what the user said

Examples:

User: "doing it"
{"intent": "PROGRESS_UPDATE", "task_title": null, "minutes": null, "summary": "User confirms they are currently working on the task"}

User: "yeah I finished the auth module"
{"intent": "COMPLETED", "task_title": null, "minutes": null, "summary": "User completed work on auth module"}

User: "going to work on the auth module for 45 minutes"
{"intent": "START_SESSION", "task_title": "auth module", "minutes": 45, "summary": "User wants to start working on auth module"}

User: "did you see that marvel trailer"
{"intent": "DISTRACTED", "task_title": null, "minutes": null, "summary": "User is talking about a movie trailer"}
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
    """Map missed check-in count to a tone mode."""
    if missed_count <= 0:
        return "neutral"
    if missed_count <= 2:
        return "strict"
    return "hostile"


# ---------------------------------------------------------------------------
# Gemini API helpers
# ---------------------------------------------------------------------------

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


async def _call_gemini(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.1,
) -> str:
    """Call the Gemini REST API and return the text response.

    Uses raw httpx instead of the SDK to keep dependencies minimal.
    """
    url = GEMINI_API_URL.format(model=model)

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 512,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            params={"key": api_key},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    # Extract text from Gemini response
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        logger.error("Unexpected Gemini response structure: %s", e)
        return ""


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
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
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
    api_key: str,
    model: str = "gemini-2.0-flash",
) -> IntentResult:
    """Parse user intent from a message using Gemini.

    On parse failure, retries once with a stricter prompt.

    Args:
        text: The user's raw message.
        session_context: Dict with active session info.
        user_context: Dict with user context.
        api_key: Gemini API key.
        model: Gemini model name.

    Returns:
        IntentResult with the classified intent.
    """
    context_str = _build_context_string(session_context, user_context)
    user_message = f"Context:\n{context_str}\n\nUser message: {text}"

    # First attempt
    try:
        raw = await _call_gemini(
            api_key=api_key,
            model=model,
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.1,
        )
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
        logger.warning("First intent parse failed, retrying")
        raw_retry = await _call_gemini(
            api_key=api_key,
            model=model,
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_message=f"{user_message}\n\n{RETRY_PROMPT}\nPrevious attempt: {raw}",
            temperature=0.0,
        )
        parsed_retry = _parse_json_response(raw_retry)

        if parsed_retry and "intent" in parsed_retry:
            return IntentResult(
                intent=parsed_retry["intent"],
                task_title=parsed_retry.get("task_title"),
                minutes=parsed_retry.get("minutes"),
                summary=parsed_retry.get("summary"),
                raw_response=raw_retry,
            )

        logger.error("Intent parsing failed after retry. Raw: %s | Retry: %s", raw, raw_retry)
        return IntentResult(intent="UNCLEAR", raw_response=raw_retry)

    except Exception as e:
        logger.exception("Gemini intent parsing error: %s", e)
        return IntentResult(intent="UNCLEAR", raw_response=str(e))


# ---------------------------------------------------------------------------
# Core: feedback generation
# ---------------------------------------------------------------------------


async def generate_feedback(
    intent: str,
    context: str,
    tone: str = "strict",
    *,
    api_key: str,
    model: str = "gemini-2.0-flash",
) -> str:
    """Generate a feedback message for the user in the specified tone.

    Args:
        intent: The classified intent.
        context: Human-readable context about the current session/task.
        tone: One of 'neutral', 'strict', 'hostile'.
        api_key: Gemini API key.
        model: Gemini model name.

    Returns:
        A short feedback string.
    """
    tone_prompt = PROMPTS.get(tone, PROMPTS["strict"])

    intent_instructions = {
        "PROGRESS_UPDATE": "The user gave a progress update. Acknowledge briefly (1 sentence max) and push them to keep going. Don't be sycophantic.",
        "DISTRACTED": "The user is off-topic and not working. Call them out bluntly. Redirect to their task.",
        "COMPLETED": "The user finished their task. One short acknowledgment, then ask what's next.",
        "START_SESSION": "The user is starting work. Confirm in one sentence. No motivational fluff.",
        "UNCLEAR": "The user's message was vague. Ask them to be specific about what they're doing right now.",
    }

    instruction = intent_instructions.get(intent, intent_instructions["UNCLEAR"])

    try:
        return await _call_gemini(
            api_key=api_key,
            model=model,
            system_prompt=f"{tone_prompt}\n\n{instruction}",
            user_message=f"Context: {context}",
            temperature=0.7,
        )
    except Exception as e:
        logger.exception("Gemini feedback generation error: %s", e)
        fallbacks = {
            "PROGRESS_UPDATE": "Got it. Keep pushing.",
            "DISTRACTED": "Focus. Get back to work.",
            "COMPLETED": "Done. What's next?",
            "START_SESSION": "Session started. Go.",
            "UNCLEAR": "What are you doing? Be specific.",
        }
        return fallbacks.get(intent, "What are you doing? Be specific.")
