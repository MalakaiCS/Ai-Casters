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

_BANTER_RULE = (
    "You share the desk with a co-commentator. When they have just spoken, you "
    "may briefly build on or answer what they said so it sounds like a real "
    "two-person conversation — but never repeat their words, and never invent "
    "facts to do it. Address them naturally, not by name."
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
    return f"{style} {_SHARED_RULES} {_BANTER_RULE} Respond in {lang}."


def user_prompt(
    directive: CommentaryDirective,
    avoid: tuple[str, ...] = (),
    conversation: tuple[tuple[str, str], ...] = (),
    speaker: str = "",
) -> str:
    """Render the event facts into a compact brief for the model.

    ``avoid`` lists lines said recently so the model varies its wording instead
    of repeating stock phrases — the most common complaint about auto-casters.
    ``conversation`` is the recent desk exchange as ``(speaker, text)`` pairs so
    this caster can react to its co-caster (banter).
    """
    facts = ", ".join(f"{k}={v}" for k, v in directive.context.items()) or "none"
    parts = [
        f"Event: {directive.topic}.",
        f"Excitement: {directive.excitement:.2f} (0=calm, 1=maximum).",
        f"Facts: {facts}.",
    ]
    if conversation:
        exchange = " ".join(
            f"[{_who(role, speaker)}] {text.strip()}" for role, text in conversation if text.strip()
        )
        if exchange:
            parts.append(f"Recent desk exchange (most recent last): {exchange}")
            last_role = conversation[-1][0]
            if speaker and last_role != speaker:
                parts.append("Your co-caster just spoke — you may briefly react to them.")
    if avoid:
        recent = " | ".join(line.strip() for line in avoid if line.strip())
        if recent:
            parts.append(
                "Do NOT repeat or lightly reword any of these recent lines; "
                f"say something fresh: {recent}."
            )
    parts.append("Produce the single spoken line now.")
    return " ".join(parts)


def _who(role: str, speaker: str) -> str:
    """Label a transcript turn from this speaker's point of view."""
    if speaker and role == speaker:
        return "you"
    return "co-caster"
