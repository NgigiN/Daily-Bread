"""Static reflection prompt bank. Deterministic rotation by day-of-year."""

from __future__ import annotations

from datetime import date

REFLECTION_PROMPTS: list[str] = [
    "What verse or phrase stood out to you today, and why?",
    "Is there a promise in today's reading you can hold onto this week?",
    "What is this passage asking you to do differently?",
    "Who could you share today's reading with?",
    "What does today's reading reveal about God's character?",
    "Where do you see yourself in today's passage?",
    "What question would you ask if you could talk to the author?",
    "Is there a command here you've been putting off obeying?",
    "What's one word that sums up today's reading?",
    "How does today's reading challenge something you believe?",
    "What would change if you took today's passage seriously this week?",
    "Is there someone in today's reading you relate to? Why?",
    "What's a practical step you can take because of what you read?",
    "What surprised you in today's reading?",
    "How does today's passage connect to something happening in your life right now?",
    "What's something you're grateful for after reading this?",
    "Is there a warning in today's reading worth paying attention to?",
    "What does today's reading teach you about prayer?",
    "Where do you need more faith after reading this?",
    "What would you tell a friend who asked what today's reading was about?",
    "Is there a pattern of sin or struggle named here that you recognize in yourself?",
    "What does today's reading say about how to treat others?",
    "What's one thing you want to remember from today's reading a week from now?",
    "How does this passage point to Jesus?",
    "What emotion did today's reading stir in you?",
    "Is there an example here worth imitating?",
    "What's something you don't understand in today's reading — and who could you ask?",
    "How would your day be different if you lived out today's passage?",
    "What does today's reading show about God's faithfulness?",
    "Is there an idol or distraction today's passage is confronting?",
    "What's a prayer you could pray in response to today's reading?",
    "Who in today's reading needed courage, and where do you need it too?",
    "What's the hardest part of today's reading to accept?",
    "How does today's reading shape how you'll spend the next 24 hours?",
    "What does today's passage say is worth valuing?",
    "Is there a relationship in today's reading you can learn from?",
    "What's one thing today's reading asks you to let go of?",
    "How does today's reading encourage you?",
    "What's a way you could obey today's reading, specifically, before the day ends?",
    "If today's reading were the only Scripture you had, what would you take from it?",
]


def prompt_for_date(day: date) -> str:
    """Deterministic prompt for a calendar date — same prompt for everyone that day."""
    index = (day.timetuple().tm_yday - 1) % len(REFLECTION_PROMPTS)
    return REFLECTION_PROMPTS[index]
