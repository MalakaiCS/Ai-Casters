"""Prompt construction for API-backed commentary providers.

The prompts encode the project's hard rules directly: use only the supplied
facts, original wording, never imitate a real caster, and output only the spoken
line. Pure functions, so they are unit-tested without any model call.
"""

from __future__ import annotations

from ai_caster.director.directives import CommentaryDirective, Speaker

_LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese",
    "de": "German",
    "fr": "French",
}

_SHARED_RULES = (
    "Use ONLY the facts provided in the event — never invent player names, "
    "numbers, weapons, or outcomes. Use original wording; do NOT imitate, quote, "
    "or reference any real-world commentator or caster. Output ONLY the spoken "
    "line: no preamble, labels, quotation marks, or stage directions."
)


def system_prompt(speaker: str, language: str = "en") -> str:
    """Build the system prompt for a speaker role."""
    lang = _LANGUAGE_NAMES.get(language, "English")
    if speaker == Speaker.PLAY_BY_PLAY.value:
        style = (
            "You are an autonomous play-by-play commentator for a Counter-Strike 2 "
            "broadcast. Call the live action in SHORT, punchy, high-energy sentences "
            "(usually one sentence)."
        )
    else:
        style = (
            "You are an autonomous analyst-desk commentator for a Counter-Strike 2 "
            "broadcast. Give measured, insightful, conversational commentary in one "
            "or two sentences."
        )
    return f"{style} {_SHARED_RULES} Respond in {lang}."


def user_prompt(directive: CommentaryDirective, avoid: tuple[str, ...] = ()) -> str:
    """Render the event facts into a compact brief for the model.

    ``avoid`` lists lines said recently so the model varies its wording instead
    of repeating stock phrases — the most common complaint about auto-casters.
    """
    facts = ", ".join(f"{k}={v}" for k, v in directive.context.items()) or "none"
    parts = [
        f"Event: {directive.topic}.",
        f"Excitement: {directive.excitement:.2f} (0=calm, 1=maximum).",
        f"Facts: {facts}.",
    ]
    if avoid:
        recent = " | ".join(line.strip() for line in avoid if line.strip())
        if recent:
            parts.append(
                "Do NOT repeat or lightly reword any of these recent lines; "
                f"say something fresh: {recent}."
            )
    parts.append("Produce the single spoken line now.")
    return " ".join(parts)
